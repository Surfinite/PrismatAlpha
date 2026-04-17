# Meta-Review: Opening Book Explorer Design Spec

> **Plan**: `docs/superpowers/specs/2026-04-10-opening-book-explorer-design.md`
> **Reviews**: 3 external reviewers
> **Date**: 2026-04-10

---

## A.1 — Review Summary Table

| Reviewer | Sentiment | Key Focus Areas | Unique Insight |
|---|---|---|---|
| R1 | Mixed-positive | UX latency, branch explosion, treemap mismatch, sidebar congestion | Suggested `st.form` for batched control changes |
| R2 | Mixed | Treemap mismatch, caching strategy, correctness edge cases, art path inconsistency | Proposed `streamlit-agraph` or `st_pyecharts` for tree; emphasized multiset bug documentation |
| R3 | Strongly critical | Over-scoped Phase 1, wrong query strategy, missing correctness definitions, color by delta | Proposed bulk-fetch + in-memory prefix tree; 3-layer caching; path table as first-class output; Plotly icicle |

---

## A.2 — Consensus Points

### All 3 reviewers flagged:

1. **Plotly treemap is NOT a decision tree** (R1, R2, R3) — The spec describes a top-down branching layout but proposes a space-filling rectangle chart. This is the most unanimous and severe finding.

2. **Remove Graphviz fallback** (R1 implied, R2, R3) — Adds Windows install pain, produces static images with no interactivity, and the spec never defines when it triggers.

3. **Branch explosion needs a hard cap** (R1, R2, R3) — Frequency thresholds alone aren't sufficient. Need `max_branches_per_level` (default ~8).

4. **Art path inconsistency** (R2, R3) — Section 3 references `icons/extracted_hd/` which doesn't contain unit art. Section 5 correctly references `images/cards/`. **Codebase confirms**: unit art is at `bin/asset/images/cards/{DisplayName}.png`, 143 files, 5-154KB each.

### 2 of 3 reviewers flagged:

5. **Immediate re-query on every slider is problematic** (R1, R3) — With 7+ sliders, Streamlit's rerun model creates painful UX. R1 suggests `st.form`, R3 suggests separating query-triggering filters from presentation-only changes.

6. **Unit selector grid won't fit in sidebar** (R1, R3) — 105 units with thumbnails in Streamlit sidebar is cramped. R1 suggests `st.popover`/modal, R3 suggests text-first selectors.

7. **Need empty state handling** (R2, R3) — Zero-game results, all branches pruned, low sample sizes need explicit messaging.

8. **Export/JSON download** (R1 implied, R2, R3) — Essential for a power-user tool and Phase 2 development.

---

## A.3 — Outlier Points (single reviewer, with merit assessment)

| Point | Reviewer | Merit |
|---|---|---|
| Bulk-fetch + in-memory prefix tree instead of recursive queries | R3 | **High merit.** Codebase confirms Wild Drone bulk fetch = 8,546 rows (~417KB). Trivially fits in memory. Eliminates N-query explosion and makes threshold changes free. |
| Three cacheable layers (rows → tree → viz) | R3 | **High merit.** Natural consequence of bulk-fetch. Threshold sliders operate on layer 2, chart type on layer 3. Only DB-affecting filters hit layer 1. |
| Color by WR delta vs baseline, not raw WR | R3 | **High merit.** Raw WR is ~50% for most nodes, making color uninformative. Delta from root highlights deviations. |
| Path table as first-class output | R3 | **High merit.** For a power-user tool, a sortable table of paths with count/freq/WR is where real analysis happens. Charts give shape, tables give answers. |
| Plotly icicle instead of treemap | R3 | **Medium merit.** Better than treemap for hierarchy, but still not a node-link tree. Worth including as an option alongside sunburst. |
| "Show SQL" debug toggle | R2 | **Medium merit.** Cheap to add, high diagnostic value. |
| Sample replay codes on node click | R2, R3 | **High merit.** Bridges analysis to actionable replay review. |
| Win rate confidence indicator | R2 | **High merit.** Nodes with <30 games have ±10-15% noise. Visual desaturation is cheap. |
| `st.form` for batched filter changes | R1 | **Medium merit.** Tradeoff: less fluid but avoids constant reloading. Middle ground is `st.form` for data filters, instant switching for chart type. |
| Performance instrumentation in UI | R3 | **Low-medium merit.** Nice for debugging but not critical for Phase 1. |
| Phase 1 over-scoped — ship one chart + table | R3 | **Debatable.** Three charts from the same data is low marginal cost in Plotly. But starting with sunburst + table and adding others if needed is reasonable. |
| Explicit `PRAGMA query_only = 1` | R3 | **Low merit.** Harmless safety net but the tool is already read-only by design. |

---

## A.4 — Category Breakdown

### 🏗️ Architecture & Design

| Feedback | Reviewer(s) | Codebase Reality | Assessment |
|---|---|---|---|
| Bulk-fetch + in-memory tree | R3 | Wild Drone = 8.5K rows, all games = 131K rows. Both fit easily in memory. | **Agree. Must-do.** Eliminates the recursive query problem entirely. |
| Three cacheable layers | R3 | `@st.cache_data` supports this directly with function-level caching | **Agree. Must-do.** |
| Reuse existing OB logic | R3 | `ob_analysis.py` has SQL filters hardcoded per function, `ob_format.py` has `_abbrev_buy()` and `UNIT_ABBREVS`. No shared helper module. | **Agree. Should-do.** Extract shared constants/helpers rather than copy-pasting SQL filters. |
| Stricter node schema with path_id | R3 | Sankey requires unique node IDs. Same `buy_hash` at different tree positions would merge. | **Agree. Must-do** if Sankey is kept. |

### ⚠️ Risks & Concerns

| Feedback | Reviewer(s) | Codebase Reality | Assessment |
|---|---|---|---|
| Treemap ≠ decision tree | All 3 | Confirmed. Plotly treemap is `px.treemap()` — nested rectangles. | **Must-do: replace.** See alternatives below. |
| Branch explosion | All 3 | At 5% threshold, turn 1 can have 5-8 branches. By turn 3: 100+ nodes possible. | **Must-do: add hard cap.** |
| Slider sluggishness | R1, R3 | Streamlit reruns full script on any widget change. 7+ sliders = pain. | **Must-do: use `st.form` for data filters, keep chart tabs outside form.** |
| Missing WR semantics | R2, R3 | Confirmed: `ob_analysis.py` uses `CASE WHEN tb.player = r.result THEN 1 ELSE 0 END` — this correctly handles P2 (player=1, result=1 = P2 win). Draws use `result=2`, excluded from WR denominator. `result=3` exists (2 rows) — unknown meaning, already excluded by `IN (0,1,2)` filter. | **Should-do: document explicitly.** Logic is correct in existing code; explorer must reuse it. |
| `buy_hash` multiset safety | R2 | Confirmed safe: `buy_hash` is comma-joined sorted list, preserves duplicates ("Drone,Drone"). The `frozenset` bug was only in `ob_format.py` comparison logic, not in the hash itself. | **Should-do: add one-line note.** |
| Caching key undefined | R2 | No caching exists yet (new code). Need to define it. | **Must-do: specify caching boundaries.** |

### 🗑️ Suggested Removals

| Feedback | Reviewer(s) | Assessment |
|---|---|---|
| Remove Graphviz fallback | R2, R3 | **Agree. Must-do.** Adds Windows system dependency for a static image that doesn't match the spec's goals. |
| Remove inline card art in tree nodes | R3 | **Agree for Phase 1.** Keep art in selector and panel headers, skip in-node art. Add later if wanted. |
| Remove HD info panels as art source | R2 | **Agree.** Cross-repo dependency, different naming. Card art from `images/cards/` is sufficient. |
| Skip Sankey for Phase 1 | R3 | **Consider.** Sunburst + tree + table covers the main perspectives. Sankey is marginal. |
| Remove "no apply button" stance | R1, R3 | **Agree. Must-do.** Use `st.form` for data-affecting filters. |

### ➕ Suggested Additions

| Feedback | Reviewer(s) | Assessment |
|---|---|---|
| Path table as first-class output | R3 | **Must-do.** Columns: path, count, frequency (parent), frequency (root), WR, WR delta, draws. |
| Export tree as JSON / CSV | R2, R3 | **Should-do.** `st.download_button` is trivial in Streamlit. |
| Sample replay codes per node | R2, R3 | **Should-do.** Store a few codes per path during tree construction. |
| WR confidence indicator | R2 | **Should-do.** Desaturate color for n<30. |
| Color by WR delta vs baseline | R3 | **Should-do.** More informative than raw WR for node coloring. Keep raw WR in tooltip. |
| "Show SQL" debug toggle | R2 | **Consider.** Cheap, useful for a power-user. |
| Loading spinners | R1 | **Should-do.** `st.spinner()` is one line. |
| Empty state messages | R2, R3 | **Must-do.** |
| `requirements.txt` | R2 | **Must-do.** |
| Performance instrumentation | R3 | **Consider.** |
| "Other" node for pruned branches | R3 | **Must-do.** Preserves frequency totals so user knows coverage. |
| Filter validation (contradictory include/exclude) | R3 | **Should-do.** |
| Testing section | R3 | **Should-do.** |

### 🔄 Alternative Approaches

| Alternative | Reviewer | Assessment |
|---|---|---|
| Plotly icicle for hierarchy | R3 | **Good option.** Better than treemap for showing hierarchy + frequency. Consider as replacement for treemap label. |
| Plotly Scatter custom tree | R2 | **Best option for interactive tree.** ~50 lines of layout code, full Plotly interactivity. |
| `st_pyecharts` ECharts tree | R2 | Available on pip. Native collapsible tree. But adds a dependency and may have Streamlit version friction. |
| `streamlit-agraph` | R2 | Available (v0.0.45). Node-link graph. But optimized for network graphs, not hierarchical trees. |
| Ship sunburst + table first, add others later | R3 | **Reasonable scoping.** Three charts from same data is low marginal cost, but prioritizing is smart. |

### ✅ Confirmed Good / Keep As-Is

- Phase 1/Phase 2 split (all 3)
- Three-file separation: data/viz/app (R2, R3)
- Read-only SQLite, `format=200` filter (R3)
- Per-turn frequency thresholds (R2)
- Comparative layout with P1/P2, Unit/Unit, With/Without modes (all 3)
- Include/exclude unit filter design (all 3)
- Nested tree data model (R2)

---

## A.5 — Conflicts & Contradictions

### Tree rendering approach

R1 suggests `st.form` and better tree labeling. R2 suggests `streamlit-agraph`, `st_pyecharts`, or custom Plotly Scatter. R3 suggests Plotly icicle + table.

**Recommendation:** Use **Plotly Scatter custom tree** for the primary "Decision Tree" tab (interactive, hover, no extra dependency), **Plotly sunburst** for the overview tab, and the **path table** as the analytical workhorse. This covers R2's best suggestion and R3's table-first philosophy. Icicle can replace sunburst if sunburst proves less useful. Sankey deferred.

### Scope: three charts or one?

R3 wants aggressive scoping (one chart + table). R1 and R2 accept three charts but want the tree fixed.

**Recommendation:** Ship two charts (custom tree + sunburst) plus the path table. Sankey deferred to Phase 1.5. This is a pragmatic middle ground — the tree and sunburst serve different analytical purposes, and both render from the same data with different Plotly calls.

### `st.form` vs immediate re-query

R1 and R3 want `st.form`. The original spec explicitly says "no apply button."

**Recommendation:** Use `st.form` for data-affecting filters (unit selector, rating, include/exclude, depth). Keep chart type tabs and per-turn threshold sliders outside the form — thresholds prune the cached tree (layer 2), chart tabs switch rendering (layer 3). Neither needs a DB re-query.

---

## A.6 — Recommended Plan Changes

### Must-do

1. **Replace treemap with Plotly Scatter custom tree** — interactive node-link layout with hover. Remove Graphviz. (R1, R2, R3)
2. **Bulk-fetch + in-memory prefix tree** — single SQL query per panel, build tree in Python, threshold pruning is instant. (R3)
3. **Three cacheable layers** — Layer 1: filtered DB rows. Layer 2: unpruned tree. Layer 3: viz-specific transform. Define `@st.cache_data` boundaries explicitly. (R2, R3)
4. **Add `max_branches_per_level`** — default 8. Excess rolls into "Other" node. (R1, R2, R3)
5. **Add "Other" node for pruned branches** — preserves frequency totals. (R3)
6. **Add path table** as first-class output alongside charts. (R3)
7. **Use `st.form`** for data-affecting filters. Threshold sliders and chart tabs stay outside. (R1, R3)
8. **Fix art path** — remove `icons/extracted_hd/` reference, use only `images/cards/`. Remove HD info panels as source. (R2, R3)
9. **Add empty state handling** — zero games, all pruned, low sample messages. (R2, R3)
10. **Add `requirements.txt`** — `streamlit plotly Pillow`. (R2)
11. **Add `buy_hash` multiset safety note** — one line confirming comma-join preserves duplicates. (R2)

### Should-do

12. **Color by WR delta vs root baseline** — raw WR in tooltip. (R3)
13. **WR confidence indicator** — desaturate color for n<30. (R2)
14. **Export JSON/CSV button** — `st.download_button`. (R2, R3)
15. **Sample replay codes per node** — store 5-10 codes per path. (R2, R3)
16. **Loading spinners** — `st.spinner()`. (R1)
17. **Text-first unit selectors** — searchable dropdown + multiselect for include/exclude. Art in headers only. (R1, R3)
18. **Filter validation** — block contradictory include/exclude, warn on low game counts. (R3)
19. **Document WR semantics** — `player=result` for wins, draws excluded from denominator. (R2, R3)
20. **Reuse `_abbrev_buy()` and `UNIT_ABBREVS`** from `ob_format.py`. (R3)
21. **Add stacked/side-by-side toggle** for comparative layout. (R1, R2)
22. **Add testing expectations** — multiset buys, P1/P2 WR, draw handling, Wild Drone regression. (R3)

### Consider (see Optional Enhancements in updated plan)

23. Skip Sankey, ship sunburst + tree + table only (R3)
24. "Show SQL" debug toggle (R2)
25. Performance instrumentation in UI (R3)
26. Plotly icicle as option/replacement for sunburst (R3)
27. Dynamic rating range bounds from DB (R2)
28. `PRAGMA query_only = 1` (R3)
29. Derive unit count from DB/cardLibrary at runtime (R2)
30. Wilson confidence interval in hover text (R3)

### Reject

- **Remove image-rich selector entirely** — R3 suggests no images at all. I recommend text-first selectors (should-do #17) but keeping small art in panel headers. Art adds recognition value for the target user who knows Prismata units by sight.
- **Ship only one chart** — R3's strongest scope-cut. Two charts (tree + sunburst) from the same data is low marginal cost and serves different analytical purposes. The path table is the real addition.

---

## A.7 — What Stays

- **Phase 1/Phase 2 split** — confirmed good by all 3 reviewers
- **Three-file separation** (data/viz/app) — confirmed good
- **Read-only SQLite with `format=200` filter** — confirmed good
- **Per-turn frequency thresholds** — confirmed good
- **Three compare modes** (P1/P2, Unit/Unit, With/Without) — confirmed good
- **Include/exclude set composition filters** — confirmed good
- **Nested tree data model** — confirmed good, will be enriched with path_id and delta fields
- **Card art from `bin/asset/images/cards/`** — confirmed correct source
