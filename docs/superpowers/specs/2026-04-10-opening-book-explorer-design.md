# Design Spec: Opening Book Explorer

> **Date**: 2026-04-10
> **Goal**: Interactive visualization tool for exploring opening book consensus data from 24k+ expert replays. Local Streamlit prototype first, then port to prismata.live as a site page.
> **Data source**: `replays.db` — 24,096 OB-eligible games (format=200, balance_passed=1, both players 2000+, parsed turn data)

---

## 1. Two-Phase Approach

**Phase 1: Streamlit prototype** — Local Python app, queries replays.db directly. All filtering and visualization. Used for rapid iteration and as a permanent power-user analysis tool.

**Phase 2: prismata.live page** — React/Next.js page on the existing site. Python export script generates static JSON. Same visualizations rebuilt in React with D3/react-d3-tree. Ships once the Streamlit design is proven.

This spec covers Phase 1 only. Phase 2 will get its own spec after the prototype stabilizes.

---

## 2. Data Layer

### Query Function

**Input parameters:**
- `unit_name` — primary unit to analyze (must be in set)
- `player` — 0 (P1) or 1 (P2)
- `min_rating`, `max_rating` — rating range filter (both players must be in range)
- `include_units` — list of units that must be in the set (up to 11)
- `exclude_units` — list of units that must NOT be in the set
- `max_depth` — turns to explore (1-5)
- `min_freq_per_turn` — list of frequency thresholds, one per turn (e.g. [0.05, 0.05, 0.10, 0.15, 0.20])

**Output:** Nested tree structure:

```python
{
    "state": "6D+2E",        # starting state description
    "total_games": 1715,     # games matching all filters
    "children": [
        {
            "buy": ["Drone", "Drone"],
            "buy_abbrev": "DD",
            "count": 1297,
            "frequency": 0.756,    # count / parent total
            "win_rate": 0.457,
            "sample_size": 1297,
            "children": [
                {
                    "buy": ["Drone", "Drone", "Engineer"],
                    "buy_abbrev": "DDE",
                    "count": 520,
                    "frequency": 0.401,  # 520/1297
                    "win_rate": 0.538,
                    ...
                }
            ]
        }
    ]
}
```

### Tree Construction Algorithm

1. Query turn 1 buys for all games matching the unit/rating/set filters
2. Group by `buy_hash`, compute frequency and win rate
3. Prune branches below the turn 1 frequency threshold
4. For each surviving branch, collect the set of replay codes that took that path
5. Query turn 2 buys filtered to those codes
6. Repeat until max_depth or no branches survive pruning

### SQL Filters (applied to all queries)

```sql
r.format = 200
AND r.balance_passed = 1
AND r.p1_rating >= :min_rating AND r.p1_rating <= :max_rating
AND r.p2_rating >= :min_rating AND r.p2_rating <= :max_rating
AND r.result IN (0, 1, 2)
```

Set composition filters use `replay_units` table:
- Include: `AND tb.code IN (SELECT code FROM replay_units WHERE unit_name = :unit)` for each included unit
- Exclude: `AND tb.code NOT IN (SELECT code FROM replay_units WHERE unit_name = :unit)` for each excluded unit

---

## 3. Visualization Layer

Three chart types, selectable via tabs. All render from the same tree data.

### Decision Tree

Top-down tree layout. Root = starting state (6D+2E for P1, 7D+2E for P2). Each node displays:
- Buy sequence (abbreviated)
- Frequency %
- Win rate % (colored red→yellow→green)
- n= sample size

Node width or opacity scaled by frequency. Unit card art images from `bin/asset/images/icons/extracted_hd/` displayed in nodes where that unit is purchased.

Branches below the frequency threshold are not shown. Collapsed/pruned branches show a "... X more" indicator with combined frequency.

### Sunburst

Plotly sunburst chart. Each ring = one turn depth. Wedge angular size = frequency. Color = win rate (HSL gradient: red at 0%, yellow at 50%, green at 100%). Hover shows buy sequence, frequency, win rate, sample size.

### Sankey

Plotly sankey diagram. One column per turn, left to right. Band width = number of games flowing through that path. Color by win rate or by buy type. Labels on each node.

### Comparative Layout

Two charts side by side. Three compare modes:
- **P1 vs P2** — same filters, different player position. Default mode.
- **Unit vs Unit** — e.g. Wild Drone left vs Vivid Drone right, same include/exclude applied to both
- **With vs Without** — same unit, left panel includes a specific co-unit, right panel excludes it

Each side gets its own chart (same type — both trees, both sunbursts, or both sankeys).

---

## 4. Controls & Filters (Sidebar)

### Unit Selector

Searchable multi-select grid with unit card art icons. 105 Dominion units displayed in a compact grid. Two sections:

- **Include** — units that must be in the randomizer set (up to 11). The primary analysis unit is always included.
- **Exclude** — units that must NOT be in the set.

Search box filters the grid as you type. Icons are small thumbnails from the extracted HD sprites.

### Other Controls

| Control | Type | Default | Description |
|---|---|---|---|
| Compare mode | Radio | P1 vs P2 | P1 vs P2 / Unit vs Unit / With vs Without |
| Second unit | Dropdown | — | Appears in Unit vs Unit mode |
| With/Without unit | Dropdown | — | Appears in With vs Without mode |
| Rating range | Dual slider | 2000–2400 | Min and max, both players must be in range |
| Turn depth | Slider | 3 | 1–5 |
| T1 frequency threshold | Slider | 5% | 1%–50% |
| T2 frequency threshold | Slider | 5% | 1%–50% |
| T3 frequency threshold | Slider | 10% | 1%–50% |
| T4 frequency threshold | Slider | 15% | 1%–50% |
| T5 frequency threshold | Slider | 20% | 1%–50% |
| Chart type | Tabs | Tree | Tree / Sunburst / Sankey |

Per-turn threshold sliders appear dynamically based on the turn depth setting. All controls trigger immediate re-query and redraw — no "apply" button.

---

## 5. Unit Card Art

Two art sources available:
- **Card art:** `bin/asset/images/cards/{DisplayName}.png` — e.g. `Wild Drone.png`, `Tarsier.png`. Full card portraits. 105+ files using display names.
- **Info panels (HD):** `<LADDER_REPO_PATH>/<ladder>-site/public/images/units/{DisplayName}_Regular_infoHD.png` — higher detail, used on the ladder site.

Use card art for thumbnails (unit selector grid, tree nodes). Fall back to text label if a file is missing.

Displayed as:
- Thumbnails in the unit selector grid
- Inline in tree nodes when that unit is purchased
- Headers for each comparison panel

---

## 6. File Structure

### New Files

| File | Responsibility |
|---|---|
| `tools/ob_explorer.py` | Streamlit app entry point, layout, controls |
| `tools/ob_explorer_data.py` | Tree construction, SQL queries, data shaping |
| `tools/ob_explorer_viz.py` | Plotly chart builders (tree, sunburst, sankey) |

### Key Dependencies

- `streamlit` — app framework
- `plotly` — sunburst, sankey, treemap charts
- `plotly` handles treemap for the tree view; `graphviz` as fallback for classic tree layout
- `Pillow` — card art image loading/resizing

### Existing Files Used (read-only)

| File | Usage |
|---|---|
| `c:/libraries/prismata-replay-parser/replays.db` | All game data |
| `bin/asset/images/cards/` | Unit card art (display name + `.png`) |
| `bin/asset/config/cardLibrary.jso` | Unit name mapping |

---

## 7. Launch

```bash
cd c:/libraries/PrismataAI
streamlit run tools/ob_explorer.py
```

---

## 8. Future (Phase 2 — prismata.live page)

Not in scope for this spec. Will be designed separately after the Streamlit prototype stabilizes. Key differences:
- Pre-computed JSON data (Python export script) instead of live DB queries
- React/D3 rendering instead of Plotly/Streamlit
- Unit art served from the site's existing asset pipeline
- URL parameters for sharing specific views (e.g. `/openings?unit=Wild+Drone&mode=p1vsp2`)
