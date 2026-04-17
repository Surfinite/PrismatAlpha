# Meta-Review: Opening Book Explorer Implementation Plan

> **Plan**: `docs/superpowers/plans/2026-04-10-opening-book-explorer.md`
> **Reviews**: 3 external reviewers
> **Date**: 2026-04-10

---

## A.1 — Review Summary Table

| Reviewer | Sentiment | Key Focus Areas | Unique Insight |
|---|---|---|---|
| R1 | Strongly positive | Architecture validation, Wilson CI praise, minor perf tips | Suggested caching `build_tree` for side-by-side; env var for DB path |
| R2 | Mixed-critical | Concrete code bugs (max_rating, stacked layout, scoping), missing Layer 2/3 cache, draft code left in, path table numerics | Found abandoned draft code in Task 3 as highest implementation risk |
| R3 | Mixed-critical | Data layer Streamlit coupling, cache architecture gap, compare mode hardcoding, buy label stability, analytical rigor | Pushed for pure data layer decoupled from Streamlit; panel-aware debug |

---

## A.2 — Consensus Points

### All 3 reviewers flagged:

1. **Layer 2/3 caching is claimed but not implemented** (R1 minor, R2 critical, R3 critical). Only `fetch_turn_data` has `@st.cache_data`. `build_tree` and `prune_tree` run on every Streamlit rerun, making chart/threshold switching slow. All three agree this must be fixed.

### 2 of 3 reviewers flagged:

2. **`max_rating` column concern** (R2, R3). Both assumed it doesn't exist. **Codebase check: `max_rating` IS a GENERATED column in the replays schema.** The query is correct. This concern is invalid.

3. **`_abbrev_buy` is a private function** (R2, R3). Both flagged importing a `_`-prefixed function as brittle. **Codebase check: `_abbrev_buy(buy_list: list[str]) -> str` works exactly as called in the plan.** It's private by convention but stable. Low risk, but wrapping it is cheap insurance.

4. **Debug section references loop-scoped variables** (R2, R3). Both noted only last panel's timings are shown. Must fix for side-by-side.

5. **Card art loading should be cached** (R1 implied, R2, R3). Trivial fix with `@st.cache_data`.

6. **Path table formats numbers as strings** (R2 implied via "cell coloring", R3 explicit). Kills sort behavior. Must keep numeric columns numeric.

7. **Compare modes hardcode P1** (R3 explicit, R2 mentioned "comparison semantics incomplete"). Unit vs Unit and With vs Without default to player 0 silently.

---

## A.3 — Outlier Points

| Point | Reviewer | Merit |
|---|---|---|
| Decouple data layer from Streamlit entirely | R3 | **High merit.** Pure functions are more testable and reusable for Phase 2. Move `@st.cache_data` to thin wrappers in app. |
| Abandoned draft code in Task 3 | R2 | **Critical merit.** Broken `_build_children` draft left in the plan before the revised version. An agentic worker will attempt to execute it. Must remove. |
| Stacked layout `cols = [st, st]` is broken | R2 | **Critical merit.** Confirmed: `st` is a module, not a container. Must use `st.container()`. |
| Timing from cached function becomes stale | R3 | **High merit.** `query_time_ms` returned from `@st.cache_data` reflects first call only. On cache hits, timing is meaningless. |
| Buy label stability (first-seen `buy_sequence`) | R3 | **Medium merit.** Multiple buy orders can map to same `buy_hash`. Using first-seen is arbitrary. Should canonicalize. |
| Tree layout uses equal child spacing | R2, R3 | **Medium merit.** Subtree-weighted spacing would be better, but equal spacing is acceptable for MVP. |
| Use SQLite read-only URI mode | R3 | **Confirmed works** on Windows Python 3.13. Trivial improvement. |
| Add pandas to requirements | R3 | **Valid.** pandas is a transitive streamlit dep but should be explicit. |
| Add player selector for Unit vs Unit / With vs Without | R3 | **Good UX addition.** Low effort. |
| Add metadata block above each panel | R3 | **Good.** Games count, baseline WR, pruned mass. |
| CSV export for path table | R3 | **Trivial addition** alongside JSON export. |
| No test file for data layer | R2, R3 | **Valid.** Inline `python -c` checks are not a substitute for a proper test file. |

---

## A.4 — Category Breakdown

### 🏗️ Architecture & Design

| Feedback | Reviewer(s) | Codebase Reality | Assessment |
|---|---|---|---|
| Decouple data layer from Streamlit | R3 | `ob_explorer_data.py` currently imports `streamlit as st` for `@st.cache_data` | **Agree. Should-do.** Make data functions pure, add cached wrappers in app. |
| Cache "panel bundle" (rows + tree) together | R3 | No existing pattern to conflict with | **Agree. Must-do.** Use `st.session_state` keyed on filter params. |
| Use SQLite read-only URI mode | R3 | Tested: `file:...?mode=ro` works on Windows Python 3.13 | **Agree. Should-do.** |
| Add player selector for non-P1vP2 modes | R3 | Compare modes currently hardcode `player=0` | **Agree. Should-do.** Simple radio widget. |

### ⚠️ Risks & Concerns

| Feedback | Reviewer(s) | Codebase Reality | Assessment |
|---|---|---|---|
| `max_rating` column doesn't exist | R2, R3 | **INVALID.** `max_rating` is a GENERATED column: `REAL GENERATED ALWAYS AS (CASE WHEN p1_rating IS NULL OR p2_rating IS NULL THEN NULL ELSE MAX(p1_rating, p2_rating) END)`. Max value: 2343.7. Query is correct. | **Reject.** No change needed. |
| Stacked layout `[st, st]` broken | R2 | `st` is a module, not a container | **Confirmed bug. Must-do fix.** |
| Only Layer 1 cached | R1, R2, R3 | No `@st.cache_data` on `build_tree` or `prune_tree` | **Confirmed. Must-do fix.** |
| Stale timing from cached function | R3 | `fetch_turn_data` returns `(rows, query_ms)` but on cache hit, `query_ms` is from original call | **Confirmed. Should-do fix.** Measure timing outside cached function. |
| Debug section scoped to last panel | R2, R3 | Loop variables overwritten each iteration | **Confirmed. Must-do fix.** |
| Abandoned draft code in Task 3 | R2 | Broken `_build_children` left in plan before revised version | **Confirmed. Must-do: remove.** |
| `_abbrev_buy` is private | R2, R3 | Signature is `(buy_list: list[str]) -> str`, works correctly | **Low risk.** Add a local wrapper for safety. |

### 🗑️ Suggested Removals

| Feedback | Reviewer(s) | Assessment |
|---|---|---|
| Remove abandoned draft code in Task 3 | R2 | **Must-do.** |
| Remove `import json` inside render loop | R2 | **Should-do.** Move to module top. |
| Remove `plotly.express as px` if unused | R3 | **Should-do.** Check if sunburst/icicle use it. They don't — `go.Sunburst` and `go.Icicle` are used directly. |
| Remove `UNIT_ABBREVS` import if unused directly | R3 | Not used directly in data module, only via `_abbrev_buy`. **Should-do: remove from data module import.** |
| Remove `submitted` variable if unused | R3 | Form button drives reruns without storing value. **Nit.** Keep for clarity. |

### ➕ Suggested Additions

| Feedback | Reviewer(s) | Assessment |
|---|---|---|
| Test file for data layer | R2, R3 | **Should-do.** At least: empty rows, single game, pruning, Wilson CI, WR correctness. |
| Player selector for compare modes | R3 | **Should-do.** |
| Panel metadata block (games, baseline WR, pruned mass) | R3 | **Should-do.** Already partially there as `st.caption`. Expand. |
| CSV export alongside JSON | R3 | **Consider.** Trivial but lower priority than JSON. |
| Compare mode validation (same unit, contradictory filters) | R2, R3 | **Should-do.** |
| Add pandas to requirements | R3 | **Should-do.** Even though it's a transitive dep. |
| Filter summary in exports | R3 | **Consider.** |
| "Other" row in path table | R3 | **Should-do.** |
| URL params via `st.query_params` | R2 | **Consider.** Nice but not MVP. |
| `__all__` exports | R2 | **Consider.** Good practice, low priority. |

### 🔧 Implementation Details & Nits

| Feedback | Reviewer(s) | Assessment |
|---|---|---|
| Path table: keep numeric columns numeric | R3 | **Must-do.** |
| Canonical buy label (not first-seen) | R3 | **Should-do.** Use sorted `buy_hash` for label rather than arbitrary `buy_sequence` order. |
| `_empty_root` uses "6D+2E" but root uses "Start" | R2 | **Nit. Should-do:** Pick one convention. Use "6D+2E"/"7D+2E" everywhere. |
| Cache `load_card_art` | R1, R2, R3 | **Should-do.** Trivial. |
| Node size formula: use `sqrt(frequency)` | R2 | **Consider.** Better visual spread. |
| `deepcopy` in pruning is expensive | R2, R3 | **Acceptable for now.** Watch if node counts grow. |
| Spinner text says "Querying..." for all phases | R3 | **Nit.** |
| `os.getenv("PRISMATA_DB")` fallback for DB path | R1 | **Consider.** |

---

## A.5 — Conflicts & Contradictions

### `max_rating` column existence

R2 and R3 both flagged `SELECT MAX(max_rating)` as a bug. **Codebase confirms it exists** as a GENERATED column. No change needed. The context document listed `p1_rating` and `p2_rating` but didn't explicitly call out the generated `max_rating` column, which misled both reviewers.

### How to implement Layer 2/3 caching

R1 suggests `@st.cache_data` on `build_tree`. R2 suggests `st.session_state`. R3 suggests a "panel bundle" cached function or decoupling from Streamlit entirely.

**Recommendation:** R3's approach is best. Make `build_tree` and `prune_tree` pure functions (no Streamlit imports). In the app, use `st.session_state` to store the unpruned tree keyed on data filter params. When only thresholds change, re-prune from the cached tree. This delivers all three layers correctly and keeps the data module reusable.

### Scope of compare mode fix

R2 notes comparison semantics are "incomplete." R3 wants a player selector for all modes. 

**Recommendation:** Add a player radio in Unit vs Unit and With vs Without modes. Low effort, high analytical value — you'd want to compare "Wild Drone P2 WITH Centurion vs WITHOUT" just as much as P1.

---

## A.6 — Recommended Plan Changes

### Must-do

1. **Remove abandoned draft code from Task 3.** The broken `_build_children` before "Step 2 (revised)" must be deleted. (R2)
2. **Implement Layer 2/3 caching via `st.session_state`.** Store unpruned tree keyed on data filter params. Prune from cached tree when thresholds change. (R1, R2, R3)
3. **Fix stacked layout: `cols = [st.container(), st.container()]`** not `[st, st]`. (R2)
4. **Fix debug section to show per-panel timings.** Collect timing into a list, display all panels. (R2, R3)
5. **Keep path table columns numeric.** Use raw floats in DataFrame, format via `st.dataframe` column config. (R3)
6. **Measure timing outside cached functions.** Don't return `query_ms` from `@st.cache_data`. (R3)

### Should-do

7. **Decouple data layer from Streamlit.** Remove `import streamlit` from `ob_explorer_data.py`. Move `@st.cache_data` to wrappers in app. (R3)
8. **Add player selector for Unit vs Unit and With vs Without modes.** (R3)
9. **Add test file** `tools/tests/test_ob_explorer_data.py` with core data layer tests. (R2, R3)
10. **Add compare mode validation** — same unit, contradictory with/include/exclude. (R2, R3)
11. **Cache `load_card_art`** with `@st.cache_data`. (R1, R2, R3)
12. **Move imports to module top** — `import json`, `import os` in app file. (R2, R3)
13. **Remove unused `plotly.express as px` import.** (R3)
14. **Add pandas to requirements.** (R3)
15. **Use SQLite read-only URI mode** `file:...?mode=ro`. (R3)
16. **Use canonical buy display label** — `_abbrev_buy(sorted(buy_list))` for label consistency. (R3)
17. **Standardize root label** — use "6D+2E"/"7D+2E" everywhere, not "Start". (R2)
18. **Add "Other" row to path table.** (R3)
19. **Expand panel metadata** — show matched games, decisive, draws, baseline WR, pruned mass. (R3)

### Consider (see Optional Enhancements in updated plan)

20. CSV export for path table (R3)
21. `os.getenv("PRISMATA_DB")` fallback (R1)
22. `sqrt(frequency)` for node sizing (R2)
23. URL params via `st.query_params` (R2)
24. `__all__` exports in modules (R2)
25. Filter summary in exports (R3)
26. Subtree-weighted tree layout (R2, R3)

### Reject

- **Fix `max_rating` query** (R2, R3) — **Invalid.** `max_rating` is a GENERATED column that exists in the schema. Query is correct.
- **Remove reliance on `_abbrev_buy`** (R3) — **Reject full removal.** The function works correctly and has the right signature. Wrapping it adds no value over importing it. The `_` prefix is a naming convention, not a stability contract in a single-developer project.

---

## A.7 — What Stays

- **Bulk-fetch + in-memory prefix tree** (all 3)
- **Three-file split** data/viz/app (all 3)
- **`st.form` for data filters, instant threshold/chart switching** (all 3)
- **Wilson CI in node schema** (R1 praised, R2/R3 agreed)
- **WR delta coloring** (all 3)
- **Scatter tree via Plotly Scatter** (all 3)
- **Icicle replacing Sankey** (all 3)
- **Path table as first-class output** (all 3)
- **"Other" node with branch capping** (all 3)
- **JSON export and debug SQL** (all 3)
- **Empty state handling** (all 3)
- **Task ordering**: data layer fully built before viz, viz before app (R1, R2)
