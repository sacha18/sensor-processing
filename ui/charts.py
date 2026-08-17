"""Shared chart-building helpers used across pipeline steps."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from ui.theme import DIVERGING_SCALE, _rgba


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


def corr_heatmap(mat: pd.DataFrame):
    zmin, zmax = float(mat.values.min()), float(mat.values.max())
    fig = px.imshow(mat, text_auto=".2f", color_continuous_scale=DIVERGING_SCALE, zmin=zmin, zmax=zmax)
    fig.update_layout(height=400, margin=dict(t=20), coloraxis_colorbar=dict(title=None))
    return fig
