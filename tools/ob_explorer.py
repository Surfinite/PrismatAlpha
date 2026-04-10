"""Opening Book Explorer — Streamlit app.

Interactive visualization of opening book consensus data from expert replays.
Launch: streamlit run tools/ob_explorer.py
"""
import json
import os
import time

import streamlit as st
from PIL import Image

from tools.ob_explorer_data import (
    build_sql_for_debug,
    build_tree,
    count_nodes,
    fetch_turn_data,
    get_connection,
    get_dominion_units,
    get_max_rating,
    prune_tree,
)
from tools.ob_explorer_viz import (
    build_path_table,
    render_icicle,
    render_sunburst,
    render_tree,
)

st.set_page_config(page_title="OB Explorer", layout="wide")

CARD_ART_DIR = "bin/asset/images/cards"


@st.cache_data(ttl=None)
def _startup():
    conn = get_connection()
    units = get_dominion_units(conn)
    max_r = get_max_rating(conn)
    conn.close()
    return units, max_r


@st.cache_data(ttl=None)
def _load_card_art(unit_name: str, size: int = 48):
    path = os.path.join(CARD_ART_DIR, f"{unit_name}.png")
    if not os.path.exists(path):
        return None
    try:
        img = Image.open(path)
        img.thumbnail((size, size))
        return img
    except Exception:
        return None


dominion_units, max_rating = _startup()

st.title("Opening Book Explorer")

# URL params for bookmarking
qp = st.query_params
default_unit = qp.get("unit", "Wild Drone") if qp.get("unit") in dominion_units else "Wild Drone"

# --- Sidebar: Data Filters (inside form) ---
with st.sidebar:
    st.header("Data Filters")

    with st.form("data_filters"):
        primary_unit = st.selectbox(
            "Primary Unit", dominion_units,
            index=dominion_units.index(default_unit) if default_unit in dominion_units else 0,
        )

        compare_mode = st.radio("Compare Mode", ["P1 vs P2", "Unit vs Unit", "With vs Without"])

        second_unit = None
        with_unit = None
        compare_player = 0
        if compare_mode == "Unit vs Unit":
            second_unit = st.selectbox("Second Unit", dominion_units, index=min(1, len(dominion_units) - 1))
            compare_player = st.radio("Player", ["P1", "P2"], horizontal=True, key="uvsu_player")
            compare_player = 0 if compare_player == "P1" else 1
        elif compare_mode == "With vs Without":
            with_unit = st.selectbox("With/Without Unit", dominion_units, index=min(1, len(dominion_units) - 1))
            compare_player = st.radio("Player", ["P1", "P2"], horizontal=True, key="wvwo_player")
            compare_player = 0 if compare_player == "P1" else 1

        include_units = st.multiselect("Include Units (must be in set)", dominion_units)
        exclude_units = st.multiselect("Exclude Units (must NOT be in set)", dominion_units)

        rating_range = st.slider("Rating Range", 1500, max_rating, (2000, max_rating), step=50)
        max_depth = st.slider("Turn Depth", 1, 5, 3)
        max_branches = st.slider("Max Branches per Level", 3, 20, 8)

        st.form_submit_button("Apply")

    # Presentation controls (outside form — instant update)
    st.header("Display")
    chart_type = st.radio("Chart Type", ["Tree", "Sunburst", "Icicle", "Path Table"])

    st.subheader("Frequency Thresholds")
    defaults = [0.05, 0.05, 0.10, 0.15, 0.20]
    thresholds = []
    for i in range(max_depth):
        default = defaults[i] if i < len(defaults) else 0.20
        val = st.slider(f"Turn {i+1}", 0.01, 0.50, default, 0.01, key=f"thresh_{i}")
        thresholds.append(val)

    layout_mode = st.radio("Layout", ["Side-by-side", "Stacked"])

# --- Validation ---
overlap = set(include_units) & set(exclude_units)
if overlap:
    st.error(f"Include/exclude overlap: {', '.join(overlap)}. Remove conflicting units.")
    st.stop()

if compare_mode == "Unit vs Unit" and second_unit == primary_unit:
    st.error("Second unit must be different from primary unit.")
    st.stop()

if compare_mode == "With vs Without" and with_unit == primary_unit:
    st.error("With/Without unit must be different from primary unit.")
    st.stop()

if compare_mode == "With vs Without" and with_unit in include_units:
    st.warning(f"{with_unit} is in the Include list — the 'Without' panel will force-exclude it.")

if compare_mode == "With vs Without" and with_unit in exclude_units:
    st.warning(f"{with_unit} is in the Exclude list — the 'With' panel will force-include it.")

# --- Build panel configs ---
def make_panel(unit, player, label):
    return {"unit": unit, "player": player, "label": label}


if compare_mode == "P1 vs P2":
    panels = [
        make_panel(primary_unit, 0, f"P1 — {primary_unit}"),
        make_panel(primary_unit, 1, f"P2 — {primary_unit}"),
    ]
elif compare_mode == "Unit vs Unit":
    p_label = "P1" if compare_player == 0 else "P2"
    panels = [
        make_panel(primary_unit, compare_player, f"{p_label} — {primary_unit}"),
        make_panel(second_unit, compare_player, f"{p_label} — {second_unit}"),
    ]
else:  # With vs Without
    p_label = "P1" if compare_player == 0 else "P2"
    panels = [
        make_panel(primary_unit, compare_player, f"{p_label} — {primary_unit} WITH {with_unit}"),
        make_panel(primary_unit, compare_player, f"{p_label} — {primary_unit} WITHOUT {with_unit}"),
    ]


# --- Caching helpers ---
def _cache_key(panel, include_extra=(), exclude_extra=()):
    inc = tuple(sorted(set(include_units) | set(include_extra)))
    exc = tuple(sorted(set(exclude_units) | set(exclude_extra)))
    return (panel["unit"], panel["player"], rating_range[0], rating_range[1],
            inc, exc, max_depth)


def get_cached_tree(panel, include_extra=(), exclude_extra=()):
    """Get or build the unpruned tree (Layer 2), cached in session_state."""
    key = _cache_key(panel, include_extra, exclude_extra)
    state_key = f"tree_{key}"

    if state_key not in st.session_state:
        inc = tuple(sorted(set(include_units) | set(include_extra)))
        exc = tuple(sorted(set(exclude_units) | set(exclude_extra)))

        t0 = time.perf_counter()
        conn = get_connection()
        rows = fetch_turn_data(
            conn, panel["unit"], panel["player"],
            float(rating_range[0]), float(rating_range[1]),
            inc, exc, max_depth,
        )
        conn.close()
        query_ms = (time.perf_counter() - t0) * 1000

        t1 = time.perf_counter()
        tree = build_tree(rows, panel["player"], max_depth)
        build_ms = (time.perf_counter() - t1) * 1000

        st.session_state[state_key] = tree
        st.session_state[f"timing_{state_key}"] = {"query_ms": query_ms, "build_ms": build_ms}
    else:
        if f"timing_{state_key}" not in st.session_state:
            st.session_state[f"timing_{state_key}"] = {"query_ms": 0, "build_ms": 0}

    return st.session_state[state_key], st.session_state[f"timing_{state_key}"]


# --- Path table column formatting ---
PATH_TABLE_COLUMN_CONFIG = {
    "Freq (parent)": st.column_config.NumberColumn(format="%.1%%"),
    "Freq (root)": st.column_config.NumberColumn(format="%.1%%"),
    "Win Rate": st.column_config.NumberColumn(format="%.1%%"),
    "WR Delta": st.column_config.NumberColumn(format="%+.1%%"),
    "CI Low": st.column_config.NumberColumn(format="%.1%%"),
    "CI High": st.column_config.NumberColumn(format="%.1%%"),
}


# --- Render panels ---
if layout_mode == "Side-by-side":
    cols = st.columns(2)
else:
    cols = [st.container(), st.container()]

panel_debug_info = []

for i, panel in enumerate(panels):
    with cols[i]:
        # Header with card art
        art = _load_card_art(panel["unit"])
        if art:
            hcol1, hcol2 = st.columns([1, 8])
            with hcol1:
                st.image(art)
            with hcol2:
                st.subheader(panel["label"])
        else:
            st.subheader(panel["label"])

        # Include/exclude overrides for With/Without mode
        inc_extra = ()
        exc_extra = ()
        if compare_mode == "With vs Without":
            if i == 0:
                inc_extra = (with_unit,)
            else:
                exc_extra = (with_unit,)

        with st.spinner("Loading..."):
            tree, timing = get_cached_tree(panel, inc_extra, exc_extra)

        if tree["count"] == 0:
            st.warning("No games match these filters.")
            panel_debug_info.append({"label": panel["label"], "count": 0})
            continue

        # Prune
        t_prune = time.perf_counter()
        pruned = prune_tree(tree, thresholds, max_branches)
        prune_ms = (time.perf_counter() - t_prune) * 1000

        if not pruned["children"]:
            st.info("All branches below threshold. Try lowering frequency thresholds.")
            panel_debug_info.append({"label": panel["label"], "count": tree["count"]})
            continue

        # Update URL params
        st.query_params.update(unit=primary_unit, mode=compare_mode)

        # Panel metadata
        total_visible = sum(c["count"] for c in pruned["children"])
        coverage = total_visible / pruned["count"] * 100 if pruned["count"] > 0 else 0
        st.caption(
            f"{pruned['count']:,} games | "
            f"WR: {pruned['win_rate']:.1%} | "
            f"Decisive: {pruned['count_decisive']:,} | "
            f"Draws: {pruned['count_draws']} | "
            f"Coverage: {coverage:.0f}%"
        )

        # Render chart
        t_render = time.perf_counter()
        if chart_type == "Tree":
            fig = render_tree(pruned, panel["label"])
            st.plotly_chart(fig, use_container_width=True)
        elif chart_type == "Sunburst":
            fig = render_sunburst(pruned, panel["label"])
            st.plotly_chart(fig, use_container_width=True)
        elif chart_type == "Icicle":
            fig = render_icicle(pruned, panel["label"])
            st.plotly_chart(fig, use_container_width=True)
        else:  # Path Table
            df = build_path_table(pruned)
            if df.empty:
                st.info("All branches below threshold.")
            else:
                st.dataframe(df, use_container_width=True, height=400,
                             column_config=PATH_TABLE_COLUMN_CONFIG)
        render_ms = (time.perf_counter() - t_render) * 1000

        # Export buttons with filter summary
        filter_summary = {
            "unit": panel["unit"], "player": panel["player"],
            "rating_range": list(rating_range), "depth": max_depth,
            "include": list(include_units) + list(inc_extra),
            "exclude": list(exclude_units) + list(exc_extra),
            "thresholds": thresholds, "max_branches": max_branches,
        }
        export_data = {"filters": filter_summary, "tree": pruned}

        col_json, col_csv = st.columns(2)
        with col_json:
            st.download_button(
                "Export JSON",
                json.dumps(export_data, indent=2, default=str),
                f"ob_{panel['unit']}_{panel['player']}.json",
                "application/json",
            )
        with col_csv:
            df_export = build_path_table(pruned)
            if not df_export.empty:
                st.download_button(
                    "Export CSV",
                    df_export.to_csv(index=False),
                    f"ob_{panel['unit']}_{panel['player']}.csv",
                    "text/csv",
                )

        panel_debug_info.append({
            "label": panel["label"],
            "count": pruned["count"],
            "nodes": count_nodes(pruned),
            "query_ms": timing["query_ms"],
            "build_ms": timing["build_ms"],
            "prune_ms": prune_ms,
            "render_ms": render_ms,
        })


# --- Debug section (per-panel) ---
with st.expander("Debug", expanded=False):
    show_sql = st.checkbox("Show SQL")
    if show_sql:
        for idx, panel in enumerate(panels):
            inc_extra = ()
            exc_extra = ()
            if compare_mode == "With vs Without":
                if idx == 0:
                    inc_extra = (with_unit,)
                else:
                    exc_extra = (with_unit,)
            inc = tuple(sorted(set(include_units) | set(inc_extra)))
            exc = tuple(sorted(set(exclude_units) | set(exc_extra)))
            st.markdown(f"**{panel['label']}**")
            sql = build_sql_for_debug(
                panel["unit"], panel["player"],
                float(rating_range[0]), float(rating_range[1]),
                inc, exc, max_depth,
            )
            st.code(sql, language="sql")

    st.markdown("**Performance (per panel)**")
    for info in panel_debug_info:
        if info.get("nodes"):
            st.text(
                f"{info['label']}: {info['count']:,} games, {info['nodes']} nodes | "
                f"Query: {info['query_ms']:.0f}ms, Build: {info['build_ms']:.0f}ms, "
                f"Prune: {info['prune_ms']:.0f}ms, Render: {info['render_ms']:.0f}ms"
            )
        else:
            st.text(f"{info['label']}: {info.get('count', 0)} games (no chart rendered)")
