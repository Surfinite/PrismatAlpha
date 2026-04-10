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
