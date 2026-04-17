# Context Document: Opening Book Explorer

> **Plan under review**: `docs/superpowers/specs/2026-04-10-opening-book-explorer-design.md`
> **Date**: 2026-04-10

---

## 1. Reviewer Brief

You are receiving two documents: this context document and a design spec for the "Opening Book Explorer."

Your role is to **critically analyze** the spec given this context. Identify:
- Weaknesses, risks, missing considerations
- Better alternatives, unnecessary complexity, things to remove
- Things that are good and should be preserved
- Additions, potential future features worth considering, architectural improvements

Be constructively critical. Your review will be synthesized in a meta-review to improve the plan, so be specific and actionable.

**Important**: You do NOT have direct access to the codebase. You are working from this context document only. The plan author has full codebase access and will validate all suggestions against the actual code during the meta-review. Flag where you feel uncertain due to limited visibility and note assumptions you are making.

### Review Output Format

1. **One-line verdict**: Overall assessment in a single sentence.
2. **What's good**: What should be kept as-is and why.
3. **Concerns & risks**: What worries you, ranked by severity.
4. **Suggested changes**: Specific, actionable modifications.
5. **Alternatives**: Different approaches worth considering.
6. **Additions**: Things missing that should be there.
7. **Removals**: Things that shouldn't be in the plan.
8. **Minor / nits**: Low-priority observations.
9. **Assumptions you're making**: Where you lacked visibility and had to guess.

Be specific. Reference section names or step numbers from the plan. Don't soften your criticism.

---

## 2. Project Overview

**PrismataAI** is a C++ game engine and AI for **Prismata**, a turn-based perfect-information strategy card game by Lunarch Studios. The project includes:
- C++ engine with Alpha-Beta and UCT/MCTS search
- A transpiled JS engine for replay analysis
- A Python replay parsing and training pipeline
- A live community site at **prismata.live** (Next.js)

**Current stage**: Mature codebase with active feature development. The opening book analysis pipeline was recently built (March 2026) and has never been visualized — only CLI text output. This spec is the first visualization layer.

**Key goals**: Build an interactive explorer for opening book consensus data so the developer (Surfinite) can analyze expert opening patterns visually, then later expose it as a community page on prismata.live.

**Constraints**:
- Solo developer, cost-conscious
- Local compute only (no cloud for this tool)
- Must work with existing SQLite database (~205k replays, ~124k parsed)
- Streamlit and Plotly are not currently installed (will need `pip install`)

**Target users**: Phase 1 = Surfinite (power-user analysis). Phase 2 = Prismata community via prismata.live.

---

## 3. Architecture & Tech Stack

### Existing Stack

| Layer | Technology |
|---|---|
| C++ Engine | Visual Studio, x86 only |
| JS Engine | Node.js, transpiled from AS3 |
| Replay Parser | Python 3.13, stdlib + sqlite3 |
| OB Analysis | Python (`replay_parser/ob_analysis.py`, `ob_format.py`) |
| Database | SQLite (WAL mode), `replays.db` at `c:/libraries/prismata-replay-parser/` |
| prismata.live | Next.js 16 + React 19 + TypeScript + Tailwind + shadcn/ui + PixiJS |

### New Stack (this spec)

| Component | Technology |
|---|---|
| App framework | Streamlit |
| Charts | Plotly (sunburst, sankey, treemap) |
| Tree layout | Plotly treemap or Graphviz fallback |
| Image handling | Pillow |
| Data access | Direct SQLite queries (read-only) |

### Data Flow

```
replays.db (SQLite, read-only)
    |
    v
ob_explorer_data.py (SQL queries, tree construction)
    |
    v
ob_explorer_viz.py (Plotly chart builders)
    |
    v
ob_explorer.py (Streamlit layout, controls, rendering)
    |
    v
Browser (localhost)
```

### Key Architectural Decisions

1. **Streamlit for Phase 1** — chosen over building directly in React because it allows rapid iteration with live DB queries. The developer can tweak filters and immediately see results without an export step.
2. **Direct DB queries** — no pre-computation or caching layer. The DB is local, read-only, and SQLite handles the query volume fine for a single user.
3. **Three visualization types** — tree, sunburst, and sankey all render from the same nested data structure. The developer wants to prototype all three to see which is most useful before committing to one for the site.
4. **Phase 2 deferred** — the prismata.live port will use pre-computed JSON (export script) and React/D3 rendering. Separate spec later.

---

## 4. Codebase Map

### PrismataAI Repository (`c:/libraries/PrismataAI/`)

```
replay_parser/              # Python package (4,529 LOC)
  ob_analysis.py            # OB consensus computation (555 LOC) — KEY
  ob_format.py              # Report/config output formatting (654 LOC)
  database.py               # Parse DB schema, ingest, backfill
  pipeline.py               # Fetch → JS extract → ingest orchestrator
  fetch.py                  # S3 replay download
  __main__.py               # CLI entry point

tools/                      # Misc scripts (will host new Streamlit app)

bin/asset/
  config/config.txt         # AI player definitions, existing opening books
  config/cardLibrary.jso    # 116 unit definitions (internal→display names)
  images/cards/             # 143 unit card art PNGs (display name + .png)
```

### Replay Parser Repository (`c:/libraries/prismata-replay-parser/`)

```
replays.db                  # Main database (205,918 replays, 124,265 parsed)
replays_archive/            # 134,177 .json.gz replay files
build_replay_db.py          # Multi-source UPSERT ingestion
replay_db.py                # Schema DDL
import_ladder.py            # NEW: imports prismata.live ladder codes
backfill_metadata.py        # NEW: fills format/version from replay JSON
```

### <ladder> Repository (`<LADDER_REPO_PATH>/`)

```
<ladder>-site/
  src/app/                  # Next.js pages (players, stats, replays, etc.)
  src/components/           # React components (PixiJS renderer, UI)
  src/lib/utils.ts          # getWinrateColor() HSL gradient
  public/images/units/      # HD unit info panels ({Name}_Regular_infoHD.png)
export_player_stats.py      # Per-player stats export
export_unit_winrates.py     # Unit winrate by ELO bracket
prismata_ladder.db          # Ladder game database (2,316 games)
```

---

## 5. Relevant Existing Patterns & Conventions

### Database Patterns
- All OB analysis queries filter: `r.format = 200 AND r.balance_passed = 1 AND r.p1_rating >= :min AND r.p2_rating >= :min AND r.result IN (0, 1, 2)`
- `turn_buys` table has `buy_hash` (sorted, comma-joined) for grouping and `buy_sequence` (JSON array, original order) for display
- `replay_units` junction table enables efficient set composition queries
- All queries are read-only against the DB

### OB Analysis Patterns
- `ob_analysis.py` already has `get_dominion_units()`, `analyze_unit_turn1()`, `analyze_unit_turn2_dd()`, `get_top_cooccurring_units()`, `analyze_pair_turn1()` — the explorer builds on the same query patterns but adds recursive tree construction
- Buy sequences are abbreviated: DD = Drone+Drone, DDE = Drone+Drone+Engineer, CDD = Conduit+Drone+Drone, EWW = Engineer+Wild Drone+Wild Drone

### Card Art
- Card art at `bin/asset/images/cards/{DisplayName}.png` (e.g. `Wild Drone.png`, `Tarsier.png`)
- 143 PNG files, named by display name
- Not all units have art files — fall back to text labels

### prismata.live Conventions
- Python export scripts generate static JSON, site reads at build/runtime
- Win rate color gradient: custom HSL function in `lib/utils.ts` (red→yellow→green, biased toward positive)
- Unit data in `data/units.ts` with resource costs, supply values

### Testing
- `replay_parser/tests/test_ob_analysis.py` has unit tests with mock data for consensus logic
- No existing Streamlit test patterns

---

## 6. Current State & Known Issues

### What Works
- 124,265 replays parsed with turn-by-turn data (turn_buys, turn_state, turn_actions)
- 26,509 OB-eligible games at 2000+ rating with format=200
- OB analysis tool generates 311 config-ready entries from CLI
- prismata.live running with 6 bots, live spectating, replay viewer
- Card art extracted and available locally

### Known Issues / Technical Debt
- **`buy_hash` multiset bug (just fixed)**: `ob_format.py` was using `frozenset` for buy comparison, collapsing duplicate units (DD → {Drone}). Fixed to use `Counter`. The explorer's data layer must also use the correct multiset representation.
- **format=NULL codes**: 28,579 replays have no `format` field. Most are from community sources (discord, getreplays) and prismata.live imports. Backfill script exists but only covers codes with local .json.gz files. The `format = 200` filter correctly excludes these from OB analysis.
- **Streamlit/Plotly not installed**: Neither package is currently in the Python environment. Will need `pip install streamlit plotly Pillow`.
- **x86 OOM concern**: Not relevant for Python tooling, only C++ engine processes.

### Recent Changes (this session, 2026-04-09)
1. Imported 2,316 prismata.live ladder codes into replays.db
2. Ran extraction pipeline — 124,265 total parsed (up from ~108k)
3. Added `r.format = 200` filter to all 5 OB analysis SQL queries
4. Built metadata backfill into the extraction pipeline (`database.py` `_backfill_replays_metadata`)
5. Fixed multiset comparison bug in `ob_format.py`
6. First-ever run of OB analysis tool — produced 311 entries, identified 8 contradictions with existing LiveOpeningBook2

---

## 7. Context Specific to the Plan

### Parts of the Codebase Touched

The explorer **creates 3 new files** (`tools/ob_explorer.py`, `tools/ob_explorer_data.py`, `tools/ob_explorer_viz.py`) and **reads from**:
- `replays.db` — all game data (turn_buys, turn_state, replays, replay_units tables)
- `bin/asset/images/cards/` — unit card art
- `bin/asset/config/cardLibrary.jso` — unit name mapping (for building the 105-unit selector)

It does NOT modify any existing files or data.

### Prior Approaches

The OB analysis tool (`ob_analysis.py`) was the first attempt at surfacing opening data. It works as a CLI producing text output and JSON reports. The explorer builds on the same SQL patterns but adds:
- Recursive multi-turn tree construction (the CLI only does turn 1 + turn 2 separately)
- Interactive filtering (the CLI has fixed thresholds via command-line args)
- Visual output (the CLI produces text tables and JSON)

### Database Schema (key tables)

**replays**: code (PK), p1_name, p2_name, p1_rating, p2_rating, result, deck (JSON), format, balance_passed, ...

**turn_buys**: code, global_turn, player, player_turn, buy_sequence (JSON), buy_hash (sorted comma-join). PK: (code, global_turn)

**turn_state**: code, global_turn, player, player_turn, gold, green, blue, red, energy, attack, units_owned (JSON), total_units

**replay_units**: code, unit_name. PK: (code, unit_name). Junction table populated by triggers on replays.deck changes.

### Performance Considerations

- The DB has 3.18M turn_buys rows. Queries with multiple include/exclude unit filters will use nested `IN (SELECT ...)` subqueries against replay_units. With proper indexes (idx_unit_name exists), these should be fast for single-user local use.
- Tree construction queries the DB once per turn depth per surviving branch. At depth 5 with 3 surviving branches per level, that's ~120 queries. Should be sub-second on local SQLite.
- Streamlit re-runs the full script on every widget change. Caching with `@st.cache_data` is essential to avoid re-querying when only the visualization type changes.

---

## 8. Scope Boundaries

### Out of Scope
- **Phase 2 (prismata.live page)**: Separate spec later. Not designed or built here.
- **Modifying existing OB analysis tool**: The explorer is additive, not a replacement for the CLI tool.
- **Writing opening book entries to config.txt**: The explorer is read-only analysis. Config changes are a manual step.
- **Training pipeline integration**: No connection to the neural net training system.
- **Multi-user or authentication**: This is a local single-user tool.

### Fixed/Non-Negotiable
- **SQLite as data source**: No migration to PostgreSQL or other DB. The existing schema is the interface.
- **`format = 200` filter**: Only ranked games. This was a deliberate data quality decision.
- **Streamlit for Phase 1**: Already decided during brainstorming. Reviewers should focus on the data layer and visualization design, not the framework choice.
- **Python 3.13 on Windows**: The development environment. Git Bash shell.

### Accepted Trade-offs
- **Two implementations** (Streamlit then React): Accepted because rapid prototyping value outweighs implementation cost. The Streamlit version persists as a power-user tool.
- **No pre-computation**: Live queries are fast enough for one user. Phase 2 will need export scripts.
- **Three chart types at once**: Potentially over-scoped, but the developer wants to prototype all three to pick the best one. May drop one or two after initial testing.

---

## 9. Success Criteria

1. **Functional**: Can select any Dominion unit, see its P1 vs P2 opening trees side by side through 3 turns, with frequency and win rate on each node.
2. **Filterable**: Rating range slider, include/exclude unit filters, and per-turn frequency thresholds all work and update the visualization immediately.
3. **Comparative**: Can switch between P1 vs P2, Unit vs Unit, and With vs Without comparison modes.
4. **Three chart types**: Tree, sunburst, and sankey all render from the same data without errors.
5. **Card art**: Unit icons visible in the selector grid and in tree nodes.
6. **Performance**: Full re-render in under 2 seconds after any control change (with caching).
7. **Reproduces known findings**: The Wild Drone analysis from the current session (EWW vs DD driven by Centurion, Energy Matrix, etc.) should be visually apparent in the explorer.

---

## 10. Key Questions for Reviewers

1. **Tree construction scalability**: The algorithm queries the DB recursively per branch per turn. At depth 5 with low frequency thresholds, the branch count could explode. Is the pruning strategy sufficient, or should there be an absolute branch limit (e.g. max 10 branches per level)?

2. **Streamlit re-rendering**: Streamlit re-executes the entire script on every widget change. With multiple sliders (5 threshold sliders + rating range + depth), this could feel sluggish. Is `@st.cache_data` sufficient, or should the data layer use a separate caching mechanism?

3. **Unit selector UX**: A 105-unit searchable grid with thumbnails in a Streamlit sidebar could be cramped. Is this feasible in Streamlit's sidebar constraints, or should it be a modal/dialog?

4. **Tree visualization library**: The spec proposes Plotly treemap as the primary tree renderer with Graphviz as fallback. Neither produces a classic top-down branching tree — Plotly treemap is a space-filling rectangle layout, Graphviz produces a proper tree but as a static image (no hover/click). Is there a better option for interactive tree rendering in Streamlit?

5. **Comparative layout**: Rendering two Plotly charts side by side in Streamlit uses `st.columns([1, 1])`. At depth 3+ with many nodes, will the charts be readable at 50% viewport width? Should there be a toggle between side-by-side and stacked/tabbed comparison?

---

## 11. Glossary / Domain Terms

| Term | Definition |
|---|---|
| **Dominion cards** | The 8 randomly selected units from a pool of ~105 that make each game unique. The other 11 "base set" units are always available. |
| **Opening book (OB)** | Hardcoded buy sequences for the first few turns, triggered by matching game state conditions. Currently 63 manual entries in `config.txt`. |
| **P1 / P2** | Player 1 (goes first, starts with 6 Drones + 2 Engineers) and Player 2 (goes second, starts with 7 Drones + 2 Engineers). |
| **DD** | Buying two Drones on turn 1 — the most common opening (75-95% frequency depending on the unit set). |
| **DDE / CDD** | Common turn 2 buys after DD. DDE = 2 Drones + Engineer. CDD = Conduit + 2 Drones. |
| **EWW** | Engineer + 2 Wild Drones — an alternative P1 turn 1 opening in Wild Drone sets (~20% frequency). |
| **DEW** | Drone + Engineer + Wild Drone — an alternative P2 turn 1 opening in Wild Drone sets (~32% frequency). |
| **EEV** | 2 Engineers + Vivid Drone — an alternative turn 1 opening in Vivid Drone sets (~25-31% frequency). |
| **buy_hash** | Sorted, comma-joined buy sequence for grouping. E.g. "Drone,Drone" or "Drone,Engineer,Wild Drone". |
| **balance_passed** | Flag indicating the game's unit costs match current card library (not an event/mutated game). |
| **format=200** | Ranked ladder games. Format 201=bot, 202-204=custom/casual. |
| **Randomizer set** | The specific 8 Dominion cards in a game. Determines available strategies. |
| **Consensus** | How strongly experts agree on an opening. "Strong" = 60%+ play the same buy. "Contested" = below 40%. |
| **Win rate (WR)** | Wins / (games - draws) for players who made a specific buy choice. |
| **prismata.live** | Community site hosting live spectating, replays, player stats, and bot matches. Next.js + React. |
| **Streamlit** | Python framework for rapid data apps. Renders widgets and charts in a browser. Re-runs the full script on every interaction. |
| **Plotly** | Python charting library with interactive hover, zoom, and click. Supports treemap, sunburst, and sankey chart types. |
