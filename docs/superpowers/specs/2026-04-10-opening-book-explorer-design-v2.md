# Design Spec: Opening Book Explorer (v2)

> **Date**: 2026-04-10
> **Goal**: Interactive visualization tool for exploring opening book consensus data from 26k+ expert replays. Local Streamlit prototype first, then port to prismata.live as a site page.
> **Data source**: `replays.db` — 26,509 OB-eligible games (format=200, balance_passed=1, both players 2000+, parsed turn data)

<!-- CHANGED: Updated game count to actual DB value (was 24,096, now 26,509 after pipeline completion and backfill) — Reviewer 2, 3 -->

---

## 1. Two-Phase Approach

**Phase 1: Streamlit prototype** — Local Python app, queries replays.db directly. All filtering and visualization. Used for rapid iteration and as a permanent power-user analysis tool.

**Phase 2: prismata.live page** — React/Next.js page on the existing site. Python export script generates static JSON. Same visualizations rebuilt in React with D3/react-d3-tree. Ships once the Streamlit design is proven.

This spec covers Phase 1 only. Phase 2 will get its own spec after the prototype stabilizes.

---

## 2. Data Layer

### Query Strategy: Bulk-Fetch + In-Memory Tree

<!-- CHANGED: Replaced recursive per-branch SQL queries with single bulk-fetch. R3's bulk-fetch approach validated: Wild Drone = 8.5K rows (~417KB), worst case all games = 131K rows (~6.3MB). Both trivially fit in memory. Eliminates N-query explosion and makes threshold changes free. — Reviewer 3 -->

**Step 1: Single SQL query** fetches all matching turn data up to `max_depth`:

```sql
SELECT tb.code, tb.player_turn, tb.buy_hash, tb.buy_sequence, r.result
FROM turn_buys tb
JOIN replays r ON tb.code = r.code
WHERE tb.player = :player
  AND tb.player_turn <= :max_depth
  AND r.format = 200
  AND r.balance_passed = 1
  AND r.p1_rating >= :min_rating AND r.p1_rating <= :max_rating
  AND r.p2_rating >= :min_rating AND r.p2_rating <= :max_rating
  AND r.result IN (0, 1, 2)
  AND tb.code IN (SELECT code FROM replay_units WHERE unit_name = :primary_unit)
  -- additional include/exclude subqueries
```

Note: `buy_hash` uses sorted comma-join which preserves duplicate unit names (e.g., `"Drone,Drone"`), avoiding the multiset bug fixed in `ob_format.py`.

<!-- CHANGED: Added explicit multiset safety note — Reviewer 2 -->

**Step 2: Build prefix tree in Python.** Group rows by code to get per-game paths. Walk each game's turn sequence, building a nested tree in memory. Compute frequency, win rate, and sample size at each node.

**Step 3: Prune tree.** Apply per-turn frequency thresholds and `max_branches_per_level` cap. Pruned branches aggregate into an "Other" node that preserves frequency totals.

<!-- CHANGED: Added "Other" node for pruned branches — Reviewer 3 -->

### Three Cacheable Layers

<!-- CHANGED: Added explicit caching architecture. Layer separation means threshold changes and chart switching never hit the DB. — Reviewers 2, 3 -->

| Layer | Cached On | Invalidated By |
|---|---|---|
| **Layer 1: Filtered DB rows** | `@st.cache_data` keyed on (unit, player, min_rating, max_rating, include_units, exclude_units, max_depth) | Changing any data filter in the form |
| **Layer 2: Unpruned full tree** | Built from Layer 1 rows | Same as Layer 1 |
| **Layer 3: Pruned tree + viz data** | Computed from Layer 2 + thresholds + max_branches | Changing threshold sliders or max_branches |

Chart type selection only changes rendering — no re-query, no re-prune. `@st.cache_data(ttl=None)` since the DB is static during a session.

### Input Parameters

- `unit_name` — primary unit to analyze (must be in set)
- `player` — 0 (P1) or 1 (P2)
- `min_rating`, `max_rating` — rating range filter (both players must be in range)
- `include_units` — list of units that must be in the set (up to 11)
- `exclude_units` — list of units that must NOT be in the set
- `max_depth` — turns to explore (1-5)
- `min_freq_per_turn` — list of frequency thresholds, one per turn
- `max_branches_per_level` — hard cap on branches per node (default 8)

<!-- CHANGED: Added max_branches_per_level parameter — Reviewers 1, 2, 3 -->

### Node Schema

<!-- CHANGED: Added stricter node schema with path_id (needed for Sankey/unique identification) and WR delta — Reviewer 3 -->

```python
{
    "path_id": "root",                  # unique prefix key
    "buy": ["Drone", "Drone"],
    "buy_abbrev": "D+D",               # from shared _abbrev_buy()
    "count": 1297,
    "count_decisive": 1280,             # excludes draws
    "count_draws": 17,
    "frequency_parent": 0.756,          # count / parent count
    "frequency_root": 0.756,            # count / root total_games
    "win_rate": 0.457,                  # wins / count_decisive
    "win_rate_delta": -0.043,           # WR - root baseline WR
    "win_rate_ci_low": 0.432,           # Wilson 95% CI lower bound
    "win_rate_ci_high": 0.482,          # Wilson 95% CI upper bound
    "sample_codes": ["abc-12345", ...], # 5-10 example replay codes
    "children": [...],
    "other_count": 42,                  # pruned branches combined
    "other_frequency": 0.032            # combined frequency of pruned
}
```

### Win Rate Semantics

<!-- CHANGED: Added explicit WR definition — Reviewers 2, 3 -->

- `result=0` means P1 wins, `result=1` means P2 wins, `result=2` means draw
- Win rate for player P: `SUM(CASE WHEN player = result THEN 1 ELSE 0 END) / (count - draws)`
- This is already the pattern used in `ob_analysis.py` — reuse, don't reimplement
- Draws are excluded from WR denominator but included in count/frequency
- Nodes with `count_decisive < 30` are marked low-confidence

### Set Composition Filters

Include/exclude filters use `replay_units` junction table:
- Include: `AND tb.code IN (SELECT code FROM replay_units WHERE unit_name = :unit)` for each included unit
- Exclude: `AND tb.code NOT IN (SELECT code FROM replay_units WHERE unit_name = :unit)` for each excluded unit
- **Validation:** Include and exclude lists must not overlap. If they do, show an error message instead of querying.

<!-- CHANGED: Added filter validation — Reviewer 3 -->

---

## 3. Visualization Layer

<!-- CHANGED: Replaced treemap with Plotly Scatter custom tree. Removed Graphviz fallback. Added path table as first-class output. — Reviewers 1, 2, 3 -->

Four output types, selectable via tabs. All render from the same pruned tree data. Sankey deferred to Phase 1.5.

<!-- APPLIED: #1 skip Sankey, #4 add icicle alongside sunburst -->

### Decision Tree (Plotly Scatter)

Custom interactive tree built with `plotly.graph_objects.Scatter`. Nodes as markers, edges as line traces. Layout computed with a simple recursive algorithm (constant x-spacing per depth, children distributed on y-axis).

Each node displays on hover:
- Buy sequence (full names)
- Frequency % (parent and root)
- Win rate % and delta vs root
- n= sample size (with low-confidence warning if <30)
- "Other" node shows combined pruned count

Node label: buy abbreviation (e.g. "D+D", "DDE"). Node color: WR delta gradient (red = below baseline, grey = neutral, green = above baseline). Raw WR in hover tooltip.

<!-- CHANGED: Color by WR delta vs baseline, not raw WR — Reviewer 3 -->

Node opacity or size scaled by frequency. Low-confidence nodes (n<30) rendered with reduced saturation.

<!-- CHANGED: Added WR confidence indicator — Reviewer 2 -->

### Sunburst

Plotly sunburst chart. Each ring = one turn depth. Wedge angular size = frequency. Color = WR delta gradient (matching tree coloring). Hover shows buy sequence, frequency, WR, WR delta, sample size.

### Icicle

<!-- APPLIED: #4 icicle alongside sunburst -->

Plotly icicle chart. Rectangular hierarchy where each row = one turn depth. Width = frequency. Color = WR delta gradient. Same data as sunburst but better for reading hierarchy depth and comparing branch sizes across turns. Available as a tab alongside sunburst.

### Path Table

<!-- CHANGED: Added path table as first-class output — Reviewer 3 -->

Sortable table showing all paths in the current tree. Columns:

| Column | Description |
|---|---|
| Path | Full buy sequence per turn (e.g. DD → DDE → ...) |
| Count | Games taking this exact path |
| Freq (parent) | Frequency relative to parent branch |
| Freq (root) | Frequency relative to all filtered games |
| Win Rate | Wins / decisive games |
| WR Delta | Win rate minus root baseline |
| Draws | Draw count |
| Codes | Link/button to show sample replay codes |

### Comparative Layout

Two panels side by side (default) or stacked (toggle). Three compare modes:

<!-- CHANGED: Added stacked/side-by-side toggle — Reviewers 1, 2 -->

- **P1 vs P2** — same filters, different player position. Default mode.
- **Unit vs Unit** — e.g. Wild Drone left vs Vivid Drone right, same include/exclude applied to both
- **With vs Without** — same unit, left panel includes a specific co-unit, right panel excludes it

Each side gets its own chart (same type — both trees, both sunbursts, or both tables).

---

## 4. Controls & Filters

<!-- CHANGED: Replaced immediate re-query with st.form for data filters. Threshold sliders and chart tabs stay outside form for instant interaction. — Reviewers 1, 3 -->

### Data Filters (inside `st.form`, requires "Apply" click)

| Control | Type | Default | Description |
|---|---|---|---|
| Primary unit | Searchable dropdown | — | Unit that must be in the set |
| Compare mode | Radio | P1 vs P2 | P1 vs P2 / Unit vs Unit / With vs Without |
| Second unit | Dropdown | — | Appears in Unit vs Unit mode |
| With/Without unit | Dropdown | — | Appears in With vs Without mode |
| Include units | Multiselect | — | Additional units that must be in set |
| Exclude units | Multiselect | — | Units that must NOT be in set |
| Rating range | Dual slider | 2000–max | Min and max (upper bound queried from DB at startup), both players must be in range |
| Turn depth | Slider | 3 | 1–5 |
| Max branches | Slider | 8 | 3–20, per level |

<!-- CHANGED: Text-first selectors (dropdown/multiselect) instead of image grid in sidebar — Reviewers 1, 3 -->

### Presentation Controls (outside form, instant update)

| Control | Type | Default | Description |
|---|---|---|---|
| Chart type | Tabs | Tree | Tree / Sunburst / Icicle / Path Table |
| T1–T5 frequency thresholds | Sliders | 5/5/10/15/20% | Dynamic based on turn depth |
| Layout | Toggle | Side-by-side | Side-by-side / Stacked |

Per-turn threshold sliders appear dynamically based on the turn depth setting. These operate on the cached tree (Layer 2 → Layer 3), not on SQL.

### Unit Art in UI

Card art from `bin/asset/images/cards/{DisplayName}.png` displayed as:
- Small thumbnail beside the selected unit name in each panel header
- NOT inline in tree nodes (text abbreviations are more analytically useful)

<!-- CHANGED: Removed inline card art in tree nodes, removed HD info panels as source — Reviewers 2, 3 -->

---

## 5. Empty States & Validation

<!-- CHANGED: Added explicit empty/error state handling — Reviewers 2, 3 -->

| Condition | Behavior |
|---|---|
| Zero games match filters | Show message: "No games match these filters. Try lowering the rating threshold or removing exclude filters." with total game count for the primary unit without filters. |
| All branches pruned | Show message: "All branches below threshold. Try lowering the frequency threshold for turn N." |
| Include/exclude overlap | Block query, show error: "Unit X is in both include and exclude lists." |
| Low sample size (<30) | Desaturate node color, add asterisk to WR display |
| Missing card art | Fall back to text label |

---

## 5b. Debug & Instrumentation

<!-- APPLIED: #2 Show SQL, #3 Performance instrumentation -->

A collapsible "Debug" section at the bottom of the page (collapsed by default):

- **Show SQL** — checkbox that displays the actual SQL query being executed. Invaluable for diagnosing unexpected results.
- **Performance** — query time, tree-build time, render time, total nodes rendered, total matching games.
- **Read-only mode** — DB opened with `PRAGMA query_only = 1` enforced.

<!-- APPLIED: #6 PRAGMA query_only -->

---

## 6. File Structure

### New Files

| File | Responsibility |
|---|---|
| `tools/ob_explorer.py` | Streamlit app entry point, layout, controls, form handling |
| `tools/ob_explorer_data.py` | Bulk SQL query, prefix tree construction, pruning, caching |
| `tools/ob_explorer_viz.py` | Plotly chart builders (scatter tree, sunburst, icicle), path table |
| `tools/requirements-explorer.txt` | `streamlit`, `plotly`, `Pillow` |

<!-- CHANGED: Added requirements file — Reviewer 2 -->

### Key Dependencies

- `streamlit` — app framework
- `plotly` — sunburst, icicle charts, custom scatter tree
- `Pillow` — card art image loading/resizing

<!-- CHANGED: Removed Graphviz dependency — Reviewers 2, 3 -->

### Existing Files Used (read-only)

| File | Usage |
|---|---|
| `c:/libraries/prismata-replay-parser/replays.db` | All game data |
| `bin/asset/images/cards/` | Unit card art (display name + `.png`) |
| `bin/asset/config/cardLibrary.jso` | Unit name mapping (fallback; prefer DB-derived list) |
| `replay_parser/ob_format.py` | Import `_abbrev_buy()`, `UNIT_ABBREVS` |

<!-- CHANGED: Reuse existing abbreviation logic rather than reimplementing — Reviewer 3 -->

---

## 7. Launch

```bash
cd c:/libraries/PrismataAI
pip install -r tools/requirements-explorer.txt
streamlit run tools/ob_explorer.py
```

---

## 8. Testing Expectations

<!-- CHANGED: Added testing section — Reviewer 3 -->

Key correctness checks to validate during development:

- **Multiset buys**: DD displays as "D+D" not "D". `buy_hash` "Drone,Drone" is not collapsed.
- **P1 vs P2 win rate**: P1 node WR should be ~45-48% (P2 advantage), P2 node WR ~52-55%. If reversed, win rate logic is wrong.
- **Draw handling**: Draws excluded from WR denominator but included in counts.
- **Wild Drone regression**: With Wild Drone selected, P1 should show ~75% DD and ~20% EWW at turn 1. P2 should show ~54% DD and ~32% DEW. The "With vs Without" mode comparing "With Centurion" vs "Without Centurion" should show Centurion pulling toward EWW/DEW (matching the analysis from the current session).
- **Include/exclude correctness**: Including unit X should only show games where X is in the set. Excluding should show the complement. Union should equal the unfiltered set.
- **"Other" node**: Sum of all visible branch frequencies + "Other" frequency should equal 100% at each level.

---

## 9. Future (Phase 2 — prismata.live page)

Not in scope for this spec. Will be designed separately after the Streamlit prototype stabilizes. Key differences:
- Pre-computed JSON data (Python export script) instead of live DB queries
- React/D3 rendering instead of Plotly/Streamlit
- Unit art served from the site's existing asset pipeline
- URL parameters for sharing specific views (e.g. `/openings?unit=Wild+Drone&mode=p1vsp2`)

---

## Applied Optional Enhancements

All 8 optional items from the meta-review were accepted and integrated into this spec:

1. Sankey deferred to Phase 1.5 (Section 3)
2. "Show SQL" debug toggle (Section 5b)
3. Performance instrumentation (Section 5b)
4. Icicle chart alongside sunburst (Section 3)
5. Dynamic rating bounds from DB (Section 4)
6. `PRAGMA query_only = 1` (Section 5b)
7. Unit list derived from DB (Section 6, existing files)
8. Wilson confidence interval in hover text (Section 2, node schema)
