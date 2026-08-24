"""ECharts-style Plotly theme, page CSS, and shared chart color constants."""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ECharts' signature look (vibrant categorical palette, soft grid, spline curves,
# gradient area fills) applied to our existing Plotly charts - same charts, same
# data flow, just restyled. Registered once, inherited by every figure below.
ECHARTS_COLORWAY = ["#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de", "#3ba272", "#fc8452", "#9a60b4", "#ea7ccc"]

COLORS = {"observed": "#91cc75", "linear_interp": "#fac858", "outlier_donor_regression": "#9a60b4",
          "donor_regression": "#fc8452", "manual_validated": "#3ba272",
          "outlier": "#5470c6", "unfilled": "#ee6666"}
# background/reference line (raw series, pre-smoothing series, ...) - readable against
# white without competing with the colored series drawn on top of it
REFERENCE_LINE_COLOR = "#8d94a3"
# marks the points a before/after comparison actually changed - shared across every
# step's before/after chart so "look here" reads the same regardless of which step
CHANGED_HIGHLIGHT_COLOR = "#ee6666"
METHOD_PRIORITY = ["hampel", "flatline", "range", "rate"]
METHOD_COLORS = {"hampel": "#5470c6", "flatline": "#9a60b4", "range": "#ee6666", "rate": "#fc8452"}
METHOD_LABELS = {"hampel": "spike (Hampel)", "flatline": "flatline/stuck", "range": "extreme value", "rate": "rate-of-change"}
CATEGORICAL_COLORS = ECHARTS_COLORWAY

# TMS-specific flag palettes - separate from METHOD_COLORS/METHOD_PRIORITY above
# (generic pipeline's per-sensor outlier methods) since TMS flags are per-channel
# and include TMS-only methods (device error, field event, freeze, ...)
TMS_QC_PRIORITY = ["device_error", "hampel", "flatline", "range", "rate", "field_event", "poor_contact"]
TMS_QC_COLORS = {
    "device_error": "#ee6666", "hampel": "#5470c6", "flatline": "#9a60b4",
    "range": "#fc8452", "rate": "#fac858", "field_event": "#3ba272", "poor_contact": "#ea7ccc",
}
TMS_QC_LABELS = {
    "device_error": "device error", "hampel": "spike (Hampel)", "flatline": "flatline/stuck",
    "range": "extreme value", "rate": "rate-of-change", "field_event": "known field event",
    "poor_contact": "poor soil contact",
}
TMS_FINAL_QC_PRIORITY = ["vwc_range", "freezing", "vwc_flatline", "field_event", "cross_channel"]
TMS_FINAL_QC_COLORS = {
    "vwc_range": "#ee6666", "freezing": "#5470c6", "vwc_flatline": "#9a60b4",
    "field_event": "#3ba272", "cross_channel": "#fc8452",
}
TMS_FINAL_QC_LABELS = {
    "vwc_range": "VWC out of range", "freezing": "soil freezing (T1)",
    "vwc_flatline": "VWC flatline/stuck", "field_event": "known field event",
    "cross_channel": "cross-channel plausibility",
}

# diverging blue<->red pair, gray neutral midpoint (palette.md); domain is scaled to
# each matrix's actual min/max rather than the theoretical [-1, 1] so cell-to-cell
# contrast is legible instead of everything landing in one narrow band of blue.
# High correlation -> red, low correlation -> blue.
DIVERGING_SCALE = [[0.0, "#5470c6"], [0.5, "#f5f7fa"], [1.0, "#ee6666"]]

HORIZONTAL_LEGEND = dict(orientation="h", yanchor="bottom", y=1.04, xanchor="left", x=0)


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def register_plotly_theme() -> None:
    pio.templates["echarts_like"] = go.layout.Template(
        layout=go.Layout(
            colorway=ECHARTS_COLORWAY,
            font=dict(family="'Segoe UI', 'Helvetica Neue', Arial, sans-serif", color="#2c3e50", size=13),
            title=dict(font=dict(size=15, color="#2c3e50")),
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            xaxis=dict(gridcolor="#eef0f5", zerolinecolor="#e3e6ec", linecolor="#e3e6ec", tickfont=dict(color="#6e7079")),
            yaxis=dict(gridcolor="#eef0f5", zerolinecolor="#e3e6ec", linecolor="#e3e6ec", tickfont=dict(color="#6e7079")),
            hoverlabel=dict(bgcolor="white", font_size=12, bordercolor="#5470c6"),
            hovermode="x unified",
            legend=dict(bgcolor="rgba(255,255,255,0)"),
            margin=dict(t=45, l=55, r=25, b=40),
        )
    )
    pio.templates.default = "echarts_like"


def inject_page_css() -> None:
    st.markdown("""
    <style>
    [data-testid="stHeader"] {
        height: 2.5rem;
    }
    [data-testid="stMainBlockContainer"] {
        padding-top: 2rem;
    }
    [data-testid="stMetric"] {
        background: #f5f7fa;
        border-radius: 10px;
        padding: 14px 16px;
        border: 1px solid #eef0f5;
    }
    [data-testid="stPlotlyChart"] {
        background: #ffffff;
        border-radius: 12px;
        border: 1px solid #eef0f5;
        padding: 8px;
        box-shadow: 0 2px 10px rgba(84, 112, 198, 0.06);
    }
    </style>
    """, unsafe_allow_html=True)
