# Commentary Knowledge Extraction — Context Instructions

> **For**: A new Claude session that will process Prismata strategy guides and game knowledge
> **Goal**: Extract, deduplicate, and organize ALL useful content for an AI game commentator's knowledge base
> **Date**: Feb 20, 2026

---

## Your Mission

You are building the knowledge base for a **live AI commentator** that will cast Prismata games on Twitch. The user will provide a large volume of strategy guides, wiki pages, forum posts, Discord messages, and other Prismata knowledge. Your job:

1. **Read the commentator plan** at `docs/plans/2026-02-20-live-commentator-plan.md` — understand what the commentator needs to know and how knowledge is structured (Tier 1/2/3 in Phase 4)
2. **Process everything the user provides** — guides, links, text dumps, screenshots, whatever
3. **Follow URLs and download content** — if the user shares links to online guides, strategy posts, wiki pages, etc., use WebFetch to retrieve them. Try to get the full content.
4. **Keep ALL unique content** — we want maximum coverage. Remove only exact duplicates (same sentences verbatim). Near-duplicates that phrase things differently should BOTH be kept — they may offer different angles useful for commentary.
5. **Organize into categories** (see below) but don't over-edit — raw is fine for now, formatting comes later
6. **Write output** to `docs/commentary-knowledge/` directory (create it)

---

## What the Commentator Needs to Know

The commentator watches live games and generates 1-2 sentence commentary per turn. It needs knowledge across these dimensions:

### Category 1: Game Fundamentals
- Resource system (gold, energy, green, blue, red, attack — which persist, which decay)
- Turn structure (action phase, breach, defense, swoosh)
- Win condition, player asymmetry (P2 extra Drone)
- How blocking/absorb works
- How breach works (attacker assigns damage)
- Construction time and invulnerability
- Chill/freeze mechanics

### Category 2: Base Set Units (11 units — in EVERY game)
- Drone, Engineer, Conduit, Blastforge, Animus
- Tarsier, Rhino, Wall, Steelsplitter, Forcefield, Gauss Cannon
- Their roles, standard purchase patterns, when each is good/bad

### Category 3: Advanced Units (~105 units — 8 random per game)
- What each unit does (cost, stats, ability)
- When each unit is strong vs weak
- Synergies between units ("Zemora is amazing with cheap red units")
- Counter-strategies ("against Tatsu Nullifier, you need...")
- Which units are considered overpowered, niche, or traps

### Category 4: Strategic Concepts
- Economy theory (how many Drones before teching?)
- Timing attacks (when to stop building economy and start attacking)
- Granularity (small attackers vs big attackers, pros/cons)
- Absorb theory (using big blockers to absorb damage efficiently)
- Tech diversity vs specialization
- Player 1 vs Player 2 opening theory
- Tempo and initiative
- Over-defense vs under-defense
- When to "go all in" vs "play for the long game"
- Breach math and when breach is inevitable

### Category 5: Openings & Build Orders
- Named openings (if any exist)
- Standard opening sequences for common sets
- Economic benchmarks ("by turn 6 you should have X Drones")
- First-buy priorities based on the random set

### Category 6: Meta Knowledge & Expert Opinions
- Which units/strategies are considered strongest at high level
- Common mistakes and how to punish them
- What makes a "good" or "bad" random set
- Famous games, players, or moments in Prismata history
- Community memes, terminology, slang

### Category 7: Commentary-Specific Phrases & Reactions
- How human casters/players describe exciting moments
- Prismata-specific terminology (e.g., "soak", "absorb", "leak", "threaten lethal")
- Things that make a Prismata turn dramatic or boring
- What would make a viewer go "whoa" vs "yawn"

---

## Processing Rules

### KEEP everything that is:
- Strategy advice (even if basic)
- Unit descriptions or evaluations
- Opening theory or build orders
- Player tips or heuristics
- Expert opinions or analysis
- Game terminology definitions
- Anything that helps understand WHY a move is good/bad
- Historical/meta context
- Community culture/memes relevant to casting
- Content from different perspectives on the same topic (keep both!)

### REMOVE only:
- Exact verbatim duplicates (same paragraph appearing twice)
- Pure noise (broken HTML, navigation menus, cookie notices from web scraping)
- Content about non-gameplay topics (company news, patch notes for already-applied patches, store/purchase info)
- Content about other games (unless comparing to Prismata)

### When in doubt: KEEP IT
Better to have redundant content than to lose a unique strategic insight. Deduplication and refinement happen in a later session.

---

## Output Structure

Write files to `docs/commentary-knowledge/`:

```
docs/commentary-knowledge/
  README.md                    # Index of what's in each file + sources
  01-game-fundamentals.md      # Category 1
  02-base-set-units.md         # Category 2
  03-advanced-units.md         # Category 3 (will be large)
  04-strategy-concepts.md      # Category 4
  05-openings-builds.md        # Category 5
  06-meta-expert.md            # Category 6
  07-commentary-phrases.md     # Category 7
  sources.md                   # Log of every source processed (URL, file, paste)
```

For each piece of content, note the source:
```markdown
### Wall — Defensive Backbone
> Source: Elyot's Strategy Guide (Discord, 2019)

The Wall is the most efficient pure blocker in the game. At 5 gold for 3 HP
of blocking, it provides the best absorb-per-gold ratio of any base set unit...
```

If a source is unclear, mark it `> Source: User-provided (unknown origin)`.

---

## How to Handle Links — RECURSIVE CRAWLING

**CRITICAL**: The user will often provide links to PAGES OF LINKS, not direct guide content. You must crawl recursively:

```
User provides: "https://example.com/prismata-guides"
    → Fetch that page
    → Find it's a list of 15 guide links
    → Fetch ALL 15 linked guides
    → Extract content from each
```

### Link Depth Strategy

**Depth 0 — User provides a URL:**
Fetch it. Determine what it is:
- A guide/article with actual content → extract it
- A link list / index / table of contents / "awesome list" → it's a **hub page**, go to Depth 1
- A forum thread listing resources → hub page, go to Depth 1
- A Reddit post with links in the body → hub page, go to Depth 1

**Depth 1 — Links found on a hub page:**
Fetch each linked guide/article. Extract content. Do NOT go deeper (depth 2) unless the user explicitly asks — avoid infinite crawling.

**Depth 2 — Only if explicitly requested:**
If a Depth 1 page also contains guide links, mention them to the user: "This page links to 8 more guides — should I follow those too?"

### Processing by Source Type

1. **Prismata Wiki** (prismata.fandom.com): Fetch the page. Extract unit stats, strategy notes, "tips" sections, and any linked strategy articles. Wiki pages often cross-link — follow links to other wiki strategy/unit pages mentioned in the content. Skip navigation/sidebar/footer noise.

2. **Reddit** (r/Prismata): Fetch the page. Extract post body AND top comments (comments often contain the best analysis). If the post is a "collection of resources" or "guide list", follow every linked guide.

3. **Forum / community posts**: Same as Reddit — follow any guide links within.

4. **Blog posts / articles** (e.g., Lunarch blog, personal blogs): Fetch and extract. If the article links to a "part 2" or "related guides", follow those.

5. **Google Docs / Notion / authenticated content**: Can't access directly. Ask user to paste content or export as text.

6. **YouTube/Twitch**: Can't watch videos. But if the user provides URLs:
   - Try fetching — sometimes video descriptions contain written guides or timestamps
   - Ask user if a transcript exists
   - Note the video in `sources.md` for potential future manual transcription

7. **Dead links**: Note them in `sources.md` as "DEAD LINK: [url] — could not retrieve". The user may have cached copies. **Try the Wayback Machine**: `https://web.archive.org/web/[url]` — Prismata content is from ~2015-2020 and many sites have gone dark.

8. **Link aggregation pages** (e.g., "Top Prismata Resources", Steam guide lists, awesome-lists):
   - Fetch the hub page
   - List ALL guide links found
   - Fetch each one
   - Report: "Found 12 guides on this page. Fetched 10, 2 were dead links."

### Reporting After Each URL Batch

After processing a URL (especially hub pages), report:
```
Fetched: [URL]
  Type: Hub page with 8 guide links
  Followed: 8 links
  Extracted: 6 guides (2 were dead)
  Dead links: [url1], [url2]
  Added to: 03-advanced-units.md (3 entries), 04-strategy-concepts.md (4 entries), 06-meta-expert.md (2 entries)
  Ready for more.
```

For each URL fetched, log it in `sources.md` with date and what was extracted.

---

## Existing Project Knowledge (Already Available)

These files are already in the repo and contain relevant content. Read them to avoid re-extracting what we already have:

| File | What's In It |
|---|---|
| `docs/wiki/PRISMATA_REFERENCE.md` | Curated game reference (resources, phases, base set, defense, breach, chill, strategy, glossary, advanced unit quick ref) |
| `bin/asset/config/cardLibrary.jso` | All 105+ units with internal names, UINames, costs, toughness, abilities. NOTE: uses internal codenames (e.g., "Brooder" = Blastforge, "Tesla Tower" = Tarsier) |
| `docs/wiki/` | 448 raw wiki pages (wikitext format) — game rules, unit pages, strategy articles |
| `training/data/unit_index.json` | 161 canonical unit names |
| `training/FEATURES.md` | Neural net feature layout (technical, but has unit attribute categories) |
| `CLAUDE.md` | Project instructions — has internal/display name mapping table, game phase description, AI architecture |

**Read `PRISMATA_REFERENCE.md` first** — it's the best existing summary and will help you recognize duplicate content in the user's guides.

**Read the name mapping in `CLAUDE.md`** (search for "Internal Name System") — you'll need this to match internal codenames (Tesla Tower, Brooder, Treant, etc.) to display names (Tarsier, Blastforge, Steelsplitter, etc.) when processing guides that use either convention.

---

## Key Internal-to-Display Name Mappings

These come up constantly. The commentator uses DISPLAY names:

| Internal (cardLibrary.jso) | Display (in-game) |
|---|---|
| Tesla Tower | Tarsier |
| Brooder | Blastforge |
| Treant | Steelsplitter |
| Elephant | Rhino |
| Blood Barrier | Forcefield |
| Minicannon | Gauss Cannon |
| House | Husk |
| Flame Kin | Gauss Charge |
| Academy | Animus |

Full 105-unit mapping is in `cardLibrary.jso` (any entry with a `UIName` field has a different display name).

---

## Session Workflow

1. Read this file and the commentator plan
2. Read `docs/wiki/PRISMATA_REFERENCE.md` to understand baseline knowledge
3. Create `docs/commentary-knowledge/` directory structure
4. Ask the user: "Ready — paste guides, share links, or point me to files. I'll process everything."
5. For each batch of content the user provides:
   a. Identify the source type and note it
   b. If it's a URL, fetch it
   c. Extract all game-relevant content
   d. Categorize into the 7 categories
   e. Append to the appropriate output file
   f. Log the source in `sources.md`
6. After each batch, briefly report: "Processed X. Added Y entries to categories Z. Ready for more."
7. When user says "done" or "that's everything":
   a. Do a final dedup pass (exact matches only)
   b. Write `README.md` index with entry counts per file
   c. Report total statistics

---

## Important Notes

- **Volume over polish**: The user said they have A LOT of data. Prioritize throughput over formatting. Get it all captured. Formatting comes in a later session.
- **No summarizing away detail**: When extracting from guides, keep the full strategic reasoning, not just conclusions. "Tarsier is good" is less useful than "Tarsier is good because it's the cheapest repeating attacker at 4 gold + 1 green, giving excellent granularity for the cost."
- **Commentary angle**: While extracting, think "what would make this useful for a commentator?" A commentator needs to know WHY things are interesting, not just WHAT the stats are.
- **Pronunciation notes**: If you encounter evidence of how unit names are pronounced (from videos, phonetic guides, community discussions), capture those separately — the TTS system needs pronunciation hints for unusual names.
