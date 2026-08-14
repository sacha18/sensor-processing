"""Streamlit demo of the generic sensor cleaning/homogenization pipeline.

Run with: streamlit run app.py
Data source: $SENSOR_DATA_DIR (falls back to the bundled sample_data/ if unset
or empty) - see pipeline.resolve_data_dir(). Any folder of `<sensor_id>.json`
or `<sensor_id>.csv` observation files works, regardless of sensor count or naming.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
from plotly.subplots import make_subplots
from scipy.cluster.hierarchy import dendrogram

import pipeline as P

st.set_page_config(page_title="Sensor cleaning pipeline", layout="wide")

# ECharts' signature look (vibrant categorical palette, soft grid, spline curves,
# gradient area fills) applied to our existing Plotly charts - same charts, same
# data flow, just restyled. Registered once, inherited by every figure below.
ECHARTS_COLORWAY = ["#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de", "#3ba272", "#fc8452", "#9a60b4", "#ea7ccc"]


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


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
.stTabs [data-baseweb="tab-list"] { gap: 4px; }
.stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0;
    padding: 8px 16px;
}
.stTabs [aria-selected="true"] {
    background-color: #5470c615;
    border-bottom: 3px solid #5470c6;
}
</style>
""", unsafe_allow_html=True)

st.title("Amálie data processor")
st.caption("Turns raw multi-sensor time series into a clean, gap-filled production dataset. "
           "Sample data is already loaded below - just open tabs **1 to 7** in order to see each cleaning "
           "step, then **Analysis** at the bottom for a before/after summary. Upload your own files anytime "
           "in Data source.")

with st.sidebar:
    st.header("Settings")
    st.caption("Defaults already work well - open a section below only if you want to fine-tune it.")
    step_min = st.selectbox("Nominal time step (min)", [15, 30, 60], index=1)

    with st.expander("Outlier detection", icon=":material/warning:"):
        st.caption("Independent methods, each catching a different fault mode - a point is dropped if ANY enabled method flags it.")

        use_hampel = st.checkbox("Spike filter (Hampel)", value=True,
                                  help="Flags a point that deviates by more than k x MAD from the median of a local window. "
                                       "A slow multi-step ramp stays inside the window's spread and is not flagged; an isolated spike is.")
        hampel_k = st.slider("MAD threshold", 3.0, 10.0, float(P.HAMPEL_K), 0.5, disabled=not use_hampel)
        hampel_hw = st.slider("Window (points each side)", 2, 10, P.HAMPEL_HALF_WINDOW, disabled=not use_hampel)
        st.divider()

        use_flatline = st.checkbox("Flatline / stuck sensor", value=True,
                                    help="Flags a run of back-to-back identical readings - a fault the Hampel filter can't see "
                                         "(a flatline has zero local spread, so it never looks like a spike).")
        flatline_min_run = st.slider("Min identical readings in a row", 3, 20, 6, disabled=not use_flatline)
        st.divider()

        use_percentile = st.checkbox("Extreme-value bounds (percentile)", value=False,
                                      help="Flags readings outside this sensor's own [low, high] percentile range - a context-free "
                                           "sanity bound (catches e.g. a sign flip or decimal-point glitch).")
        pct_lo, pct_hi = st.slider("Keep percentile range", 0.0, 100.0, (0.5, 99.5), disabled=not use_percentile)
        st.divider()

        use_rate = st.checkbox("Rate-of-change (max jump)", value=False,
                                help="Flags a step whose jump exceeds k x this sensor's typical step size. Self-calibrating, "
                                     "but has no window context, so genuine rapid ramps get flagged too - opt-in only.")
        rate_k = st.slider("Jump threshold (x typical step)", 2.0, 20.0, 8.0, disabled=not use_rate)

    with st.expander("Gap filling", icon=":material/timeline:"):
        max_gap = st.slider("Max gap linearly interpolated (steps)", 1, 12, P.MAX_INTERP_GAP)
        st.caption("Beyond this many missing steps, filling switches to regression against the most correlated sensor (\"donor\").")

    with st.expander("Post-processing", icon=":material/insights:"):
        agg_freq_label = st.selectbox("Aggregation period", ["Hourly", "Daily", "Weekly"], index=1)
        AGG_FREQ_MAP = {"Hourly": "1h", "Daily": "1D", "Weekly": "1W"}
        agg_freq = AGG_FREQ_MAP[agg_freq_label]
        st.caption("Summary stats (mean/min/max/std/count) per sensor over this bucket, computed on the cleaned+gap-filled series.")
        st.divider()

        smooth_method = st.selectbox("Smoothing method", ["mean", "median"], index=0)
        smooth_window = st.slider("Smoothing window (steps, centered)", 1, 21, P.SMOOTH_WINDOW, step=2)
        st.caption("A rolling average/median laid over the cleaned series to show trend without high-frequency noise - shown alongside, not instead of, the cleaned data.")

outlier_cfg = {
    "use_hampel": use_hampel, "hampel_half_window": hampel_hw, "hampel_k": hampel_k,
    "use_flatline": use_flatline, "flatline_min_run": flatline_min_run,
    "use_percentile": use_percentile, "pct_low": pct_lo, "pct_high": pct_hi,
    "use_rate": use_rate, "rate_k": rate_k,
}


@st.cache_data(show_spinner="Running pipeline...")
def get_pipeline(raw_long, step_min, outlier_cfg, max_gap, agg_freq, smooth_window, smooth_method):
    return P.process_pipeline(raw_long, step_min=step_min, outlier_cfg=outlier_cfg, max_interp_gap=max_gap,
                               agg_freq=agg_freq, smooth_window=smooth_window, smooth_method=smooth_method)


COLORS = {"observed": "#91cc75", "linear_interp": "#fac858", "donor_regression": "#fc8452",
          "outlier": "#5470c6", "unfilled": "#ee6666"}
# background/reference line (raw series, pre-smoothing series, ...) - readable against
# white without competing with the colored series drawn on top of it
REFERENCE_LINE_COLOR = "#8d94a3"
METHOD_PRIORITY = ["hampel", "flatline", "range", "rate"]
METHOD_COLORS = {"hampel": "#5470c6", "flatline": "#9a60b4", "range": "#ee6666", "rate": "#fc8452"}
METHOD_LABELS = {"hampel": "spike (Hampel)", "flatline": "flatline/stuck", "range": "extreme value", "rate": "rate-of-change"}
CATEGORICAL_COLORS = ECHARTS_COLORWAY

# diverging blue<->red pair, gray neutral midpoint (palette.md); domain is scaled to
# each matrix's actual min/max rather than the theoretical [-1, 1] so cell-to-cell
# contrast is legible instead of everything landing in one narrow band of blue.
# High correlation -> red, low correlation -> blue.
DIVERGING_SCALE = [[0.0, "#5470c6"], [0.5, "#f5f7fa"], [1.0, "#ee6666"]]


def corr_heatmap(mat: pd.DataFrame):
    zmin, zmax = float(mat.values.min()), float(mat.values.max())
    fig = px.imshow(mat, text_auto=".2f", color_continuous_scale=DIVERGING_SCALE, zmin=zmin, zmax=zmax)
    fig.update_layout(height=400, margin=dict(t=20), coloraxis_colorbar=dict(title=None))
    return fig


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


HORIZONTAL_LEGEND = dict(orientation="h", yanchor="bottom", y=1.04, xanchor="left", x=0)


def to_csv_bytes(df: pd.DataFrame, index: bool = True) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=index)
    return buf.getvalue().encode("utf-8")


# device telemetry (battery, radio signal, enclosure temp/humidity, firmware
# version, ...) rides along in the same export as real measurement channels but
# isn't a physical quantity to clean/compare - excluded from the pipeline by
# default (still selectable manually) so it doesn't dilute similarity/outlier
# results or get treated as if it were a comparable sensor
TELEMETRY_KEYWORDS = ["battery", "signal", "internal", "repeatcounter", "verfw", "credit"]


def is_telemetry_channel(sensor_id: str) -> bool:
    low = sensor_id.lower()
    return any(kw in low for kw in TELEMETRY_KEYWORDS)


# ---- data source ---------------------------------------------------------------
with st.expander("Data source", expanded=True, icon=":material/upload_file:"):
    st.caption("No file? No problem - the bundled sample data loads automatically below.")
    uploaded_files = st.file_uploader(
        "Drop your sensor files here (one file per sensor)",
        type=["json", "csv"], accept_multiple_files=True,
        help="JSON or CSV, same columns either way: phenomenon_time, result (observation_id optional). "
             "The filename (without extension) becomes that sensor's id.",
    )

    if uploaded_files:
        source_label = f"{len(uploaded_files)} uploaded file(s)"
        try:
            raw_long = P.load_raw_from_uploads(uploaded_files)
        except Exception as e:
            st.error(f"Could not parse the uploaded files: {e}")
            st.stop()
    else:
        try:
            data_dir = P.resolve_data_dir()
        except FileNotFoundError as e:
            st.error(str(e))
            st.stop()
        source_label = str(data_dir)
        raw_long = P.load_raw(data_dir)

    all_channel_ids = sorted(raw_long["sensor_id"].unique())
    default_channels = [s for s in all_channel_ids if not is_telemetry_channel(s)]
    with st.expander(f"Select channels to include ({len(default_channels)}/{len(all_channel_ids)} by default)", icon=":material/tune:"):
        st.caption("Device telemetry (battery, radio signal, enclosure temp/humidity, firmware version, ...) is "
                   "excluded by default - only real measurement channels feed the pipeline. Adjust if needed.")
        included_channels = st.multiselect("Channels", all_channel_ids, default=default_channels,
                                            label_visibility="collapsed")
    if not included_channels:
        st.error("No channels selected - pick at least one to run the pipeline.")
        st.stop()
    raw_long = raw_long[raw_long["sensor_id"].isin(included_channels)].reset_index(drop=True)

    with st.expander("Optional: unit labels per sensor", icon=":material/straighten:"):
        st.caption("Different sensors rarely measure the same thing (a piezometer in cm, a flow gauge in L/s, "
                   "a scintillometer in W/m2, ...) - drop a small mapping file to label charts accordingly. "
                   "Display only, doesn't affect any computation. CSV with sensor_id,unit columns, or JSON {\"sensor_id\": \"unit\"}.")
        units_file = st.file_uploader("Unit mapping file", type=["json", "csv"], key="units_uploader", label_visibility="collapsed")

    units = {}
    if units_file is not None:
        try:
            units = P.parse_units_mapping(units_file.name, units_file.getvalue())
        except Exception as e:
            st.warning(f"Could not parse the unit mapping file: {e}")

    st.caption(f"Data source: **{source_label}** - each phase below shows the data before/after that step.")

    r = get_pipeline(raw_long, step_min=step_min, outlier_cfg=outlier_cfg, max_gap=max_gap,
                      agg_freq=agg_freq, smooth_window=smooth_window, smooth_method=smooth_method)
    SENSORS = sorted(r["reg_long"]["sensor_id"].unique())
    # display-only label, e.g. "V3 (L/s)" when a unit was supplied - never used in computation
    SENSOR_LABEL = {s: (f"{s} ({units[s]})" if units.get(s) else s) for s in SENSORS}
    SENSOR_COLOR = {s: CATEGORICAL_COLORS[i % len(CATEGORICAL_COLORS)] for i, s in enumerate(SENSORS)}

tabs = st.tabs([
    "1. Loading", "2. Deduplication", "3. Homogenization", "4. Outliers",
    "5. Similarity", "6. Gap filling", "7. Production dataset",
])

# ---- 1. load -----------------------------------------------------------------
with tabs[0]:
    with st.expander("Raw data", expanded=True, icon=":material/table_chart:"):
        raw = r["raw_long"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Sensors", raw["sensor_id"].nunique())
        c2.metric("Raw observations", len(raw))
        c3.metric("Time span covered", f"{(raw['timestamp'].max() - raw['timestamp'].min())}")
        summary = raw.groupby("sensor_id").agg(n=("value_raw", "size"),
                                                start=("timestamp", "min"),
                                                end=("timestamp", "max"),
                                                min_val=("value_raw", "min"),
                                                max_val=("value_raw", "max")).reset_index()
        summary.insert(1, "unit", summary["sensor_id"].map(units).fillna(""))
        summary[["min_val", "max_val"]] = summary[["min_val", "max_val"]].round(2)
        st.dataframe(summary, width='stretch')
        st.dataframe(raw.head(20), width='stretch')

# ---- 2. dedupe -----------------------------------------------------------------
with tabs[1]:
    with st.expander("Duplicate sensor_id + timestamp pairs", expanded=True, icon=":material/content_copy:"):
        dup = r["dup_report"]
        if dup.empty:
            st.success("No duplicates found in this dataset.")
        else:
            st.warning(f"{len(dup)} duplicate (sensor, timestamp) pairs - keeping the most recent observation (max observation_id).")
            st.dataframe(dup, width='stretch')
        st.caption(f"Rows before: {len(r['raw_long'])} -> after deduplication: {len(r['deduped'])}")

# ---- 3. regularize -------------------------------------------------------------
with tabs[2]:
    with st.expander("Regular time grid", expanded=True, icon=":material/grid_on:"):
        st.write(f"Common grid at **{step_min} min** steps, from `{r['grid'].min()}` to `{r['grid'].max()}` ({len(r['grid'])} slots).")
        st.dataframe(r["span"].reset_index(), width='stretch')

        miss = r["reg_long"].groupby("sensor_id").agg(
            slots=("value_raw", "size"),
            missing=("value_raw", lambda s: s.isna().sum()),
        ).reset_index()
        miss["% missing"] = (100 * miss["missing"] / miss["slots"]).round(1)
        st.dataframe(miss, width='stretch')
        st.caption("A slot only counts as \"missing\" if it falls within that sensor's own deployment window (no fabricated data outside its measurement period).")

# ---- 4. outliers -----------------------------------------------------------------
with tabs[3]:
    with st.expander("Outlier detection (multiple methods)", expanded=True, icon=":material/warning:"):
        st.caption("Each enabled method (see sidebar) flags a different fault mode; a point is dropped if ANY of them flag it. "
                   "Colors below show which method caught each point (when several agree, priority is spike > flatline > extreme value > rate-of-change).")
        qc = r["qc_long"].copy()
        qc["outlier_method"] = None
        for m in METHOD_PRIORITY:
            mask = qc[f"is_outlier_{m}"] & qc["outlier_method"].isna()
            qc.loc[mask, "outlier_method"] = m

        out_rows = qc[qc["is_outlier"]]
        cols = st.columns(5)
        cols[0].metric("Total outliers", len(out_rows))
        for c, m in zip(cols[1:], METHOD_PRIORITY):
            c.metric(METHOD_LABELS[m], int(qc[f"is_outlier_{m}"].sum()))

        if len(out_rows):
            st.dataframe(out_rows[["sensor_id", "timestamp", "value_raw", "outlier_method"]], width='stretch')

        st.write("**All sensors - raw with outliers**")
        fig = facet_grid([SENSOR_LABEL[s] for s in SENSORS])
        seen_methods = set()
        for i, s in enumerate(SENSORS, start=1):
            sub = qc[qc["sensor_id"] == s].sort_values("timestamp")
            fig.add_trace(go.Scatter(x=sub["timestamp"], y=sub["value_raw"], mode="lines", connectgaps=True,
                                      line=dict(color=REFERENCE_LINE_COLOR), showlegend=False), row=i, col=1)
            for m in METHOD_PRIORITY:
                out = sub[sub["outlier_method"] == m]
                if len(out):
                    fig.add_trace(go.Scatter(x=out["timestamp"], y=out["value_raw"], mode="markers",
                                              marker=dict(color=METHOD_COLORS[m], size=9, line=dict(width=1, color="white")),
                                              name=METHOD_LABELS[m], legendgroup=m, showlegend=(m not in seen_methods)), row=i, col=1)
                    seen_methods.add(m)
        fig.update_layout(height=230 * len(SENSORS), margin=dict(t=70),
                           legend=HORIZONTAL_LEGEND)
        plot(fig)

        st.write("**Single sensor detail**")
        sensor_pick = st.selectbox("Sensor to display", SENSORS, key="outlier_sensor")
        sub = qc[qc["sensor_id"] == sensor_pick].sort_values("timestamp")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=sub["timestamp"], y=sub["value_raw"], mode="lines", connectgaps=True,
                                  line=dict(color=REFERENCE_LINE_COLOR), name="raw"))
        for m in METHOD_PRIORITY:
            out = sub[sub["outlier_method"] == m]
            if len(out):
                fig.add_trace(go.Scatter(x=out["timestamp"], y=out["value_raw"], mode="markers",
                                          marker=dict(color=METHOD_COLORS[m], size=10, line=dict(width=1, color="white")),
                                          name=METHOD_LABELS[m]))
        fig.update_layout(height=350, title=f"{SENSOR_LABEL[sensor_pick]} - raw with outliers", margin=dict(t=40))
        plot(fig)

# ---- 5. similarity -----------------------------------------------------------------
with tabs[4]:
    with st.expander("Similarity between sensors", expanded=True, icon=":material/hub:"):
        sim = r["sim"]
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Correlation on levels**")
            plot(corr_heatmap(sim["cor_level"]))
        with c2:
            st.write("**Correlation on differences**")
            plot(corr_heatmap(sim["cor_diff"]))
        st.caption("Color scale is anchored on each matrix's actual min/max (not ±1) to maximize contrast between pairs.")

        st.write("**Hierarchical clustering** (distance = 1 - |level correlation|)")
        if sim["linkage"] is None:
            st.info("Only one sensor in this dataset - nothing to cluster against.")
        else:
            dend = dendrogram(sim["linkage"], labels=sim["labels"], no_plot=True)
            order = dend["ivl"]
            fig = go.Figure()
            for xs, ys in zip(dend["icoord"], dend["dcoord"]):
                fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=ECHARTS_COLORWAY[0], width=2), showlegend=False))
            fig.update_xaxes(tickmode="array", tickvals=[5 + 10 * i for i in range(len(order))], ticktext=order)
            fig.update_layout(height=350, margin=dict(t=20), yaxis_title="distance")
            plot(fig)

        st.write("**\"Donor\" sensor selected for regression-based gap filling**")
        donor_df = pd.DataFrame({"sensor_id": list(sim["donor_of"].keys()), "donor": list(sim["donor_of"].values())})
        st.dataframe(donor_df, width='stretch')

# ---- 6. gap filling -----------------------------------------------------------------
with tabs[5]:
    with st.expander("Gap filling", expanded=True, icon=":material/timeline:"):
        with st.expander("What do the colors mean?", icon=":material/palette:"):
            st.markdown(
                "Charts reuse the same color coding for how each point was handled:\n\n"
                "- **observed** (green) - a real, untouched reading\n"
                "- **interpolated** (yellow) - a short gap, filled by straight-line interpolation\n"
                "- **donor-filled** (orange) - a longer gap, filled by regression against the most similar sensor\n"
                "- **outlier** (blue) - flagged as a fault and excluded from the cleaned series\n"
                "- **unfilled** (red) - gap too long and no similar sensor available, left empty"
            )

        prod = r["production"]
        counts = prod.groupby(["sensor_id", "fill_method"]).size().unstack(fill_value=0)
        st.dataframe(counts, width='stretch')

        def add_sensor_traces(fig, sub, row=None, col=None, legend=False):
            fig.add_trace(go.Scatter(x=sub["timestamp"], y=sub["value_clean"], mode="lines", line_shape="spline",
                                      line=dict(color=REFERENCE_LINE_COLOR), showlegend=False), row=row, col=col)
            for status, color in COLORS.items():
                if status == "outlier":
                    continue
                m = sub["fill_method"] == status
                if m.any():
                    fig.add_trace(go.Scatter(x=sub.loc[m, "timestamp"], y=sub.loc[m, "value_clean"],
                                              mode="markers", marker=dict(color=color, size=6, line=dict(width=0.5, color="white")),
                                              name=status, legendgroup=status, showlegend=legend), row=row, col=col)
            m = sub["is_outlier"]
            if m.any():
                fig.add_trace(go.Scatter(x=sub.loc[m, "timestamp"], y=sub.loc[m, "value_raw"],
                                          mode="markers", marker=dict(color=COLORS["outlier"], size=8, symbol="x"),
                                          name="outlier (raw)", legendgroup="outlier (raw)", showlegend=legend), row=row, col=col)

        st.write("**All sensors - cleaned and gap-filled series**")
        fig = facet_grid([SENSOR_LABEL[s] for s in SENSORS])
        for i, s in enumerate(SENSORS, start=1):
            sub = prod[prod["sensor_id"] == s].sort_values("timestamp")
            add_sensor_traces(fig, sub, row=i, col=1, legend=(i == 1))
        fig.update_layout(height=230 * len(SENSORS), margin=dict(t=70),
                           legend=HORIZONTAL_LEGEND)
        plot(fig)

        st.write("**Single sensor detail**")
        sensor_pick2 = st.selectbox("Sensor to display", SENSORS, key="fill_sensor")
        sub = prod[prod["sensor_id"] == sensor_pick2].sort_values("timestamp")
        fig = go.Figure()
        add_sensor_traces(fig, sub, legend=True)
        fig.update_layout(height=400, title=f"{SENSOR_LABEL[sensor_pick2]} - cleaned and gap-filled series", margin=dict(t=40))
        plot(fig)

# ---- 7. production dataset -----------------------------------------------------------------
with tabs[6]:
    with st.expander("Production dataset", expanded=True, icon=":material/inventory_2:"):
        st.write("**All sensors - final series**")
        fig = facet_grid([SENSOR_LABEL[s] for s in SENSORS])
        for i, s in enumerate(SENSORS, start=1):
            sub = r["production_wide"][s]
            add_area_trace(fig, sub.index, sub.values, SENSOR_COLOR[s], row=i, col=1)
        fig.update_layout(height=200 * len(SENSORS), margin=dict(t=40))
        plot(fig)

        st.write("**All sensors overlaid** (each series standardized to mean 0 / std 1, to compare timing and shape despite very different scales/units)")
        wide = r["production_wide"]
        standardized = (wide - wide.mean()) / wide.std()
        fig = go.Figure()
        for s in SENSORS:
            fig.add_trace(go.Scatter(x=standardized.index, y=standardized[s], mode="lines", line_shape="spline",
                                      line=dict(color=SENSOR_COLOR[s], width=1.5), name=s))
        fig.update_layout(height=420, margin=dict(t=45), yaxis_title="standardized value (z-score)",
                           legend=HORIZONTAL_LEGEND)
        plot(fig)

        st.write("Long format (one row per sensor x timestamp, with method traceability):")
        st.dataframe(r["production"], width='stretch', height=300)

        st.write("Wide format (one column per sensor, ready for analysis):")
        st.dataframe(r["production_wide"], width='stretch', height=300)

        c1, c2 = st.columns(2)
        c1.download_button("Download (long) CSV", to_csv_bytes(r["production"].set_index("timestamp")),
                            file_name="sensors_clean_long.csv", mime="text/csv", icon=":material/download:")
        c2.download_button("Download (wide) CSV", to_csv_bytes(r["production_wide"]),
                            file_name="sensors_clean_wide.csv", mime="text/csv", icon=":material/download:")

with st.expander("Analysis", expanded=False, icon=":material/insights:"):
    st.caption("Downstream analysis of the finished production dataset - nothing here feeds back into the pipeline.")

    with st.expander("Before vs after cleaning", expanded=True, icon=":material/compare_arrows:"):
        st.caption("What the pipeline actually changed: raw input (with outliers and gaps) against the final cleaned+gap-filled series.")

        fm_counts = r["production"]["fill_method"].value_counts()
        n_total = len(r["production"])
        n_reconstructed = fm_counts.get("linear_interp", 0) + fm_counts.get("donor_regression", 0)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Untouched (observed)", f"{100 * fm_counts.get('observed', 0) / n_total:.1f}%" if n_total else "-")
        c2.metric("Reconstructed", f"{100 * n_reconstructed / n_total:.1f}%" if n_total else "-",
                  help="Filled by interpolation or donor-sensor regression.")
        c3.metric("Outliers removed", int(r["qc_long"]["is_outlier"].sum()))
        c4.metric("Still unfilled", f"{100 * fm_counts.get('unfilled', 0) / n_total:.1f}%" if n_total else "-")

        raw_stats = r["reg_long"].groupby("sensor_id")["value_raw"].agg(count="count", mean="mean", std="std", min="min", max="max")
        clean_stats = r["production"].groupby("sensor_id")["value_clean"].agg(count="count", mean="mean", std="std", min="min", max="max")
        compare = raw_stats.join(clean_stats, lsuffix="_raw", rsuffix="_clean").round(3)
        compare = compare[["count_raw", "count_clean", "mean_raw", "mean_clean", "std_raw", "std_clean",
                            "min_raw", "min_clean", "max_raw", "max_clean"]]
        st.dataframe(compare, width='stretch')

        st.write("**All sensors - raw vs cleaned**")
        fig = facet_grid([SENSOR_LABEL[s] for s in SENSORS])
        for i, s in enumerate(SENSORS, start=1):
            raw_sub = r["reg_long"][r["reg_long"]["sensor_id"] == s].sort_values("timestamp")
            clean_sub = r["production_wide"][s]
            # raw drawn wider + dashed, cleaned drawn on top thinner + solid - so raw still
            # peeks out as a dashed "halo" even where the two lines are pixel-identical
            fig.add_trace(go.Scatter(x=raw_sub["timestamp"], y=raw_sub["value_raw"], mode="lines",
                                      line=dict(color=REFERENCE_LINE_COLOR, width=4, dash="dot"), name="raw", legendgroup="raw",
                                      showlegend=(i == 1)), row=i, col=1)
            fig.add_trace(go.Scatter(x=clean_sub.index, y=clean_sub.values, mode="lines", line_shape="spline",
                                      line=dict(color=SENSOR_COLOR[s], width=2), name="cleaned", legendgroup="cleaned",
                                      showlegend=(i == 1)), row=i, col=1)
        fig.update_layout(height=200 * len(SENSORS), margin=dict(t=70),
                           legend=HORIZONTAL_LEGEND)
        plot(fig)

        st.write("**All sensors - distribution shift**")
        fig = make_subplots(rows=1, cols=len(SENSORS), subplot_titles=[SENSOR_LABEL[s] for s in SENSORS])
        for i, s in enumerate(SENSORS, start=1):
            raw_vals = r["reg_long"].loc[r["reg_long"]["sensor_id"] == s, "value_raw"].dropna()
            clean_vals = r["production_wide"][s].dropna()
            fig.add_trace(go.Box(y=raw_vals, name="raw", fillcolor=_rgba(REFERENCE_LINE_COLOR, 0.25),
                                  line=dict(color=REFERENCE_LINE_COLOR), marker=dict(color=REFERENCE_LINE_COLOR),
                                  legendgroup="raw", showlegend=(i == 1)), row=1, col=i)
            fig.add_trace(go.Box(y=clean_vals, name="cleaned", fillcolor=_rgba(SENSOR_COLOR[s], 0.25),
                                  line=dict(color=SENSOR_COLOR[s]), marker=dict(color=SENSOR_COLOR[s]),
                                  legendgroup="cleaned", showlegend=(i == 1)), row=1, col=i)
        fig.update_layout(height=400, margin=dict(t=70),
                           legend={**HORIZONTAL_LEGEND, "y": 1.08})
        plot(fig)

    with st.expander(f"Aggregation ({agg_freq_label.lower()})", expanded=True, icon=":material/bar_chart:"):
        st.caption("Per-sensor summary stats over each period, computed on the cleaned+gap-filled series.")
        agg = r["agg"]
        agg_display = agg.copy()
        agg_display[["mean", "min", "max", "std"]] = agg_display[["mean", "min", "max", "std"]].round(2)
        st.dataframe(agg_display, width='stretch', height=280)

        st.write(f"**All sensors - mean per {agg_freq_label.lower()} period**")
        fig = facet_grid([SENSOR_LABEL[s] for s in SENSORS])
        for i, s in enumerate(SENSORS, start=1):
            sub = agg[agg["sensor_id"] == s]
            fig.add_trace(go.Bar(x=sub["period"], y=sub["mean"],
                                  error_y=dict(type="data", array=sub["std"], visible=True),
                                  marker=dict(color=SENSOR_COLOR[s]), showlegend=False), row=i, col=1)
        fig.update_layout(height=200 * len(SENSORS), margin=dict(t=40))
        plot(fig)

        st.download_button("Download aggregated CSV", to_csv_bytes(agg, index=False),
                            file_name=f"sensors_agg_{agg_freq}.csv", mime="text/csv", icon=":material/download:")

    with st.expander(f"Smoothing ({smooth_method}, window={smooth_window} steps)", expanded=True, icon=":material/show_chart:"):
        st.caption("Rolling smoothing layered over the cleaned series - shown alongside it, not replacing it, so the underlying QC'd data stays available.")

        st.write("**All sensors - smoothed**")
        fig = facet_grid([SENSOR_LABEL[s] for s in SENSORS])
        for i, s in enumerate(SENSORS, start=1):
            sub = r["smoothed_wide"][s]
            add_area_trace(fig, sub.index, sub.values, SENSOR_COLOR[s], row=i, col=1)
        fig.update_layout(height=200 * len(SENSORS), margin=dict(t=40))
        plot(fig)

        st.write("**Single sensor detail**")
        sensor_pick3 = st.selectbox("Sensor to display", SENSORS, key="smooth_sensor")
        raw_s = r["production_wide"][sensor_pick3]
        smooth_s = r["smoothed_wide"][sensor_pick3]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=raw_s.index, y=raw_s.values, mode="lines", line_shape="spline",
                                  line=dict(color=REFERENCE_LINE_COLOR, width=4, dash="dot"), name="cleaned (full resolution)"))
        add_area_trace(fig, smooth_s.index, smooth_s.values, SENSOR_COLOR[sensor_pick3],
                        name=f"{smooth_method} (window={smooth_window})", showlegend=True, width=2.5)
        fig.update_layout(height=400, title=f"{SENSOR_LABEL[sensor_pick3]} - cleaned vs smoothed", margin=dict(t=40),
                           legend={**HORIZONTAL_LEGEND, "y": -0.15})
        plot(fig)
