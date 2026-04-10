"""Opening book explorer — visualization layer.

Plotly chart builders (scatter tree, sunburst, icicle) and path table.
All functions take a pruned tree dict and return Plotly figures or
pandas DataFrames.
"""
import pandas as pd
import plotly.graph_objects as go

__all__ = [
    "wr_delta_color", "render_tree", "render_sunburst",
    "render_icicle", "build_path_table",
]


def wr_delta_color(delta):
    """Map WR delta to RGB color. Red (negative) -> grey (zero) -> green (positive)."""
    clamped = max(-0.15, min(0.15, delta))
    t = (clamped + 0.15) / 0.30  # 0..1
    r = int(220 - 170 * t)
    g = int(50 + 170 * t)
    b = 80
    return f"rgb({r},{g},{b})"


import math as _math


def _leaf_count(node):
    """Count leaf nodes in subtree (for weighted layout)."""
    if not node["children"]:
        return 1
    return sum(_leaf_count(c) for c in node["children"])


def _layout_tree(node, positions, x, y, x_span):
    """Recursive tree layout: y-spacing per depth, x-space weighted by subtree leaf count."""
    positions[node["path_id"]] = (x, y)
    children = node["children"]
    if not children:
        return
    leaf_counts = [_leaf_count(c) for c in children]
    total_leaves = sum(leaf_counts)
    if total_leaves == 0:
        total_leaves = len(children)
        leaf_counts = [1] * len(children)
    cursor_x = x - x_span / 2
    for child, leaves in zip(children, leaf_counts):
        child_span = x_span * leaves / total_leaves
        child_x = cursor_x + child_span / 2
        _layout_tree(child, positions, child_x, y + 1, child_span)
        cursor_x += child_span


def _empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper",
                       showarrow=False, font=dict(size=16, color="#888"))
    fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False),
                      margin=dict(l=20, r=20, t=20, b=20), height=300)
    return fig


def render_tree(tree: dict, title: str = "") -> go.Figure:
    """Render a pruned tree as an interactive Plotly scatter plot."""
    if tree["count"] == 0:
        return _empty_figure("No games match filters")

    positions = {}
    _layout_tree(tree, positions, x=0.0, y=0.0, x_span=1.0)

    node_x, node_y, node_text, node_hover, node_color, node_size = [], [], [], [], [], []
    edge_x, edge_y = [], []

    def _collect(node):
        px, py = positions[node["path_id"]]
        node_x.append(px)
        node_y.append(-py)

        node_text.append(node["buy_abbrev"])

        confidence = " [LOW SAMPLE]" if node["count_decisive"] < 30 else ""
        hover = (
            f"<b>{node['buy_abbrev']}</b><br>"
            f"Buy: {', '.join(node['buy']) if node['buy'] else 'Start'}<br>"
            f"Games: {node['count']} ({node['frequency_parent']:.1%} of parent, "
            f"{node['frequency_root']:.1%} of all)<br>"
            f"WR: {node['win_rate']:.1%} ({node['win_rate_delta']:+.1%} vs baseline)<br>"
            f"CI: [{node['win_rate_ci_low']:.1%}, {node['win_rate_ci_high']:.1%}]<br>"
            f"Decisive: {node['count_decisive']}, Draws: {node['count_draws']}"
            f"{confidence}"
        )
        if node["other_count"] > 0:
            hover += f"<br>Other: {node['other_count']} ({node['other_frequency']:.1%})"
        node_hover.append(hover)

        node_color.append(wr_delta_color(node["win_rate_delta"]))
        node_size.append(max(10, min(40, 10 + 30 * _math.sqrt(node["frequency_root"]))))

        for child in node["children"]:
            cx, cy = positions[child["path_id"]]
            edge_x.extend([px, cx, None])
            edge_y.extend([-py, -cy, None])
            _collect(child)

    _collect(tree)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y, mode="lines",
        line=dict(color="#888", width=1), hoverinfo="none",
    ))
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y, mode="markers+text",
        marker=dict(size=node_size, color=node_color, line=dict(width=1, color="#333")),
        text=node_text, textposition="top center", textfont=dict(size=10),
        hovertext=node_hover, hoverinfo="text",
    ))
    fig.update_layout(
        title=title, showlegend=False,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        margin=dict(l=20, r=20, t=40, b=20), height=500,
    )
    return fig


def _flatten_tree_for_plotly(tree: dict) -> tuple[list, list, list, list, list, list]:
    """Flatten tree into parallel lists for Plotly hierarchical charts."""
    ids, labels, parents, values, colors, hovers = [], [], [], [], [], []

    def _walk(node, parent_id=""):
        nid = node["path_id"]
        ids.append(nid)
        labels.append(node["buy_abbrev"])
        parents.append(parent_id)
        values.append(node["count"])
        colors.append(node["win_rate_delta"])

        confidence = " [LOW]" if node["count_decisive"] < 30 else ""
        hover = (
            f"{node['buy_abbrev']}: {node['count']} games "
            f"({node['frequency_parent']:.1%})<br>"
            f"WR: {node['win_rate']:.1%} ({node['win_rate_delta']:+.1%}){confidence}"
        )
        hovers.append(hover)

        for child in node["children"]:
            _walk(child, nid)

        if node["other_count"] > 0:
            other_id = f"{nid}/__other__"
            ids.append(other_id)
            labels.append(f"Other ({node['other_count']})")
            parents.append(nid)
            values.append(node["other_count"])
            colors.append(0.0)
            hovers.append(f"Pruned: {node['other_count']} ({node['other_frequency']:.1%})")

    _walk(tree)
    return ids, labels, parents, values, colors, hovers


def render_sunburst(tree: dict, title: str = "") -> go.Figure:
    if tree["count"] == 0:
        return _empty_figure("No games match filters")
    ids, labels, parents, values, colors, hovers = _flatten_tree_for_plotly(tree)
    fig = go.Figure(go.Sunburst(
        ids=ids, labels=labels, parents=parents, values=values,
        marker=dict(colors=[wr_delta_color(c) for c in colors]),
        hovertext=hovers, hoverinfo="text", branchvalues="total",
    ))
    fig.update_layout(title=title, margin=dict(l=20, r=20, t=40, b=20), height=500)
    return fig


def render_icicle(tree: dict, title: str = "") -> go.Figure:
    if tree["count"] == 0:
        return _empty_figure("No games match filters")
    ids, labels, parents, values, colors, hovers = _flatten_tree_for_plotly(tree)
    fig = go.Figure(go.Icicle(
        ids=ids, labels=labels, parents=parents, values=values,
        marker=dict(colors=[wr_delta_color(c) for c in colors]),
        hovertext=hovers, hoverinfo="text", branchvalues="total",
    ))
    fig.update_layout(title=title, margin=dict(l=20, r=20, t=40, b=20), height=500)
    return fig


def build_path_table(tree: dict) -> pd.DataFrame:
    """Flatten tree into a sortable path table with numeric columns."""
    rows = []

    def _walk(node, path_parts):
        current_path = path_parts + ([node["buy_abbrev"]] if node["buy"] else [])

        if node["buy"]:  # skip root
            rows.append({
                "Path": " > ".join(current_path),
                "Count": node["count"],
                "Freq (parent)": node["frequency_parent"],
                "Freq (root)": node["frequency_root"],
                "Win Rate": node["win_rate"],
                "WR Delta": node["win_rate_delta"],
                "CI Low": node["win_rate_ci_low"],
                "CI High": node["win_rate_ci_high"],
                "Draws": node["count_draws"],
                "Codes": ", ".join(node["sample_codes"][:5]),
            })

        for child in node["children"]:
            _walk(child, current_path)

        # "Other" row for pruned branches
        if node["other_count"] > 0 and node["buy"]:
            rows.append({
                "Path": " > ".join(current_path + ["(Other)"]),
                "Count": node["other_count"],
                "Freq (parent)": node["other_frequency"],
                "Freq (root)": node["other_count"] / tree["count"] if tree["count"] > 0 else 0,
                "Win Rate": None,
                "WR Delta": None,
                "CI Low": None,
                "CI High": None,
                "Draws": None,
                "Codes": "",
            })

    _walk(tree, [])

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    return df.sort_values("Count", ascending=False).reset_index(drop=True)
