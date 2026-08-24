"""Shared chart-building helpers used across pipeline steps."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from ui.theme import DIVERGING_SCALE, HORIZONTAL_LEGEND, REFERENCE_LINE_COLOR, _rgba


def gradient_fill(hex_color: str, top_alpha: float = 0.35) -> dict:
    """ECharts-style vertical gradient area fill, fading to transparent at the baseline."""
    return dict(type="vertical", colorscale=[[0, _rgba(hex_color, 0.0)], [1, _rgba(hex_color, top_alpha)]])


def add_area_trace(fig, x, y, color, row=None, col=None, name=None, showlegend=False, width=2):
    """A spline line with an ECharts-style gradient fill down to the series' own
    minimum (not y=0 - these sensors rarely range anywhere near zero, so a
    tozeroy fill would just paint most of the chart solid)."""
    baseline = float(np.nanmin(y))
    fig.add_trace(go.Scatter(x=x, y=[baseline] * len(x), mode="lines", line=dict(width=0),
                              hoverinfo="skip", showlegend=False), row=row, col=col)
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line_shape="spline",
                              line=dict(color=color, width=width), fill="tonexty",
                              fillgradient=gradient_fill(color), name=name, showlegend=showlegend),
                  row=row, col=col)


def plot(fig):
    """st.plotly_chart with scroll-wheel zoom off AND axes fixed-range -
    scrollZoom alone still lets Plotly's drag layer swallow the wheel event
    on some subplot/heatmap figures, intermittently blocking page scroll
    instead of scrolling past the chart. Fixing the axis range removes that
    drag-zoom listener entirely; hover/tooltips are unaffected. Centralized
    here so every chart in the app gets the fix."""
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    st.plotly_chart(fig, width='stretch', config={"scrollZoom": False})


def facet_grid(titles):
    """Vertically stacked, x-linked subplot grid, one row per title - the
    layout every "all sensors" chart in this app shares."""
    return make_subplots(rows=len(titles), cols=1, shared_xaxes=True,
                          subplot_titles=titles, vertical_spacing=0.4 / len(titles))


def facet_grid_before_after(titles, before_label: str = "Before", after_label: str = "After"):
    """Side-by-side before/after subplot grid, one row per title - left
    column is `before_label`, right is `after_label`. Y-axis is shared
    within each row (so a value change is a visible vertical shift between
    the two panels, not just a different scale) and x-axis is shared within
    each column (same as facet_grid, so every row's timeline lines up)."""
    n = len(titles)
    return make_subplots(rows=n, cols=2, shared_xaxes=True, shared_yaxes=True,
                          row_titles=list(titles), column_titles=[before_label, after_label],
                          horizontal_spacing=0.04, vertical_spacing=0.4 / n)


def run_edges(mask: pd.Series) -> pd.Series:
    """True only at the first and last point of each contiguous run of True
    in `mask` - lets a "difference" chart mark where a change starts/ends
    instead of one marker per point, which turns into a solid smear of
    overlapping circles when hundreds of consecutive readings changed (e.g.
    a blanket signal rescale, or a long stuck-sensor flatline run). A lone
    changed point is both its own start and end, so isolated single-point
    changes still get marked individually - nothing is lost there."""
    if not mask.any():
        return mask
    m = mask.to_numpy()
    starts = m & ~np.r_[False, m[:-1]]
    ends = m & ~np.r_[m[1:], False]
    return pd.Series(starts | ends, index=mask.index)


def diff_mask(before: pd.Series, after: pd.Series, atol: float = 1e-9, rtol: float = 1e-6) -> pd.Series:
    """True where `after` actually differs from `before` - a changed value, or a
    value that appeared/disappeared (NaN on only one side). Both-NaN is not a
    difference. Used to scope every before/after chart to only the points (or
    only the sensors/panels) a step actually touched."""
    b = before.to_numpy(dtype=float)
    a = after.to_numpy(dtype=float)
    both_nan = np.isnan(b) & np.isnan(a)
    close = np.isclose(b, a, atol=atol, rtol=rtol, equal_nan=False)
    return pd.Series(~(both_nan | close), index=before.index)


def before_after_chart(x, before: pd.Series, after: pd.Series, after_color: str, changed_color: str,
                        before_name: str = "Before", after_name: str = "After", changed_name: str = "changed",
                        height: int = 380, connectgaps_after: bool = True):
    """Before/after as two side-by-side panels (not overlaid) - left is
    `before`, right is `after`, sharing a y-axis so a level/range shift is
    directly comparable. Points where the two actually differ (diff_mask)
    are called out as open-circle markers in both panels - at the before
    value on the left, and at the after value on the right (or still at the
    before value if after is now NaN - a point that got dropped, not just
    changed). Returns (fig, mask) so callers can skip rendering entirely
    when mask is all-False (before == after)."""
    mask = diff_mask(before, after)
    edges = run_edges(mask)
    marker_y_after = after.where(after.notna(), before)
    fig = make_subplots(rows=1, cols=2, shared_yaxes=True,
                         subplot_titles=[before_name, after_name], horizontal_spacing=0.05)
    fig.add_trace(go.Scatter(x=x, y=before, mode="lines", connectgaps=True,
                              line=dict(color=REFERENCE_LINE_COLOR), showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=after, mode="lines", connectgaps=connectgaps_after,
                              line=dict(color=after_color), showlegend=False), row=1, col=2)
    if edges.any():
        fig.add_trace(go.Scatter(x=x[edges], y=before[edges], mode="markers", name=changed_name,
                                  marker=dict(color=changed_color, size=9, symbol="circle-open", line=dict(width=2)),
                                  legendgroup="changed", showlegend=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=x[edges], y=marker_y_after[edges], mode="markers", name=changed_name,
                                  marker=dict(color=changed_color, size=9, symbol="circle-open", line=dict(width=2)),
                                  legendgroup="changed", showlegend=False), row=1, col=2)
    fig.update_layout(height=height, margin=dict(t=40), legend=HORIZONTAL_LEGEND)
    return fig, mask


def corr_heatmap(mat: pd.DataFrame):
    zmin, zmax = float(mat.values.min()), float(mat.values.max())
    fig = px.imshow(mat, text_auto=".2f", color_continuous_scale=DIVERGING_SCALE, zmin=zmin, zmax=zmax)
    fig.update_layout(height=400, margin=dict(t=20), coloraxis_colorbar=dict(title=None))
    return fig
