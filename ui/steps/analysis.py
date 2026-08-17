"""Step 8: Analysis - similarity/clustering, before/after, aggregation, smoothing."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from scipy.cluster.hierarchy import dendrogram

import pipeline as P
from ui.charts import add_area_trace, corr_heatmap, facet_grid, plot
from ui.data_source import SensorMeta
from ui.format import to_csv_bytes
from ui.theme import ECHARTS_COLORWAY, HORIZONTAL_LEGEND, REFERENCE_LINE_COLOR, _rgba

ANALYSIS_AGG_OPTIONS = {"Hourly": "1h", "Daily": "1D", "Weekly": "1W", "Monthly": "1ME"}
STAT_OPTIONS = {"Mean": "mean", "Minimum": "min", "Maximum": "max", "Std dev": "std"}
STAT_DASH = {"mean": "solid", "min": "dot", "max": "dash", "std": "dashdot"}


def render(r: dict, sensors: SensorMeta, smooth_method: str, smooth_window: int) -> None:
    st.subheader("Analysis", divider="gray")
    st.caption("Downstream analysis of the finished production dataset - nothing here feeds back into the pipeline.")

    st.subheader(":material/hub: Similarity between sensors", divider="gray")
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

    st.subheader(":material/compare_arrows: Before vs after cleaning", divider="gray")
    st.caption("What the pipeline actually changed: raw input (with outliers and gaps) against the final cleaned+gap-filled series.")

    fm_counts = r["production"]["fill_method"].value_counts()
    n_total = len(r["production"])
    # not by fill_method name (new categories - e.g. manual_validated - keep landing here for free):
    # reconstructed = touched by the pipeline/a human AND has a value; unfilled = no value regardless of label
    n_reconstructed = int(((r["production"]["fill_method"] != "observed") & r["production"]["value_clean"].notna()).sum())
    n_unfilled = int(r["production"]["value_clean"].isna().sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Untouched (observed)", f"{100 * fm_counts.get('observed', 0) / n_total:.1f}%" if n_total else "-")
    c2.metric("Reconstructed", f"{100 * n_reconstructed / n_total:.1f}%" if n_total else "-",
              help="Filled by interpolation, regression against a correlated donor sensor, or manual validation.")
    c3.metric("Outliers removed", int(r["qc_long"]["is_outlier"].sum()))
    c4.metric("Still unfilled", f"{100 * n_unfilled / n_total:.1f}%" if n_total else "-")

    raw_stats = r["reg_long"].groupby("sensor_id")["value_raw"].agg(count="count", mean="mean", std="std", min="min", max="max")
    clean_stats = r["production"].groupby("sensor_id")["value_clean"].agg(count="count", mean="mean", std="std", min="min", max="max")
    compare = raw_stats.join(clean_stats, lsuffix="_raw", rsuffix="_clean").round(3)
    compare = compare[["count_raw", "count_clean", "mean_raw", "mean_clean", "std_raw", "std_clean",
                        "min_raw", "min_clean", "max_raw", "max_clean"]]
    st.dataframe(compare, width='stretch')

    st.write("**All sensors - raw vs cleaned**")
    fig = facet_grid([sensors.label[s] for s in sensors.ids])
    for i, s in enumerate(sensors.ids, start=1):
        raw_sub = r["reg_long"][r["reg_long"]["sensor_id"] == s].sort_values("timestamp")
        clean_sub = r["production_wide"][s]
        # raw drawn wider + dashed, cleaned drawn on top thinner + solid - so raw still
        # peeks out as a dashed "halo" even where the two lines are pixel-identical
        fig.add_trace(go.Scatter(x=raw_sub["timestamp"], y=raw_sub["value_raw"], mode="lines",
                                  line=dict(color=REFERENCE_LINE_COLOR, width=4, dash="dot"), name="raw", legendgroup="raw",
                                  showlegend=(i == 1)), row=i, col=1)
        fig.add_trace(go.Scatter(x=clean_sub.index, y=clean_sub.values, mode="lines", line_shape="spline",
                                  line=dict(color=sensors.color[s], width=2), name="cleaned", legendgroup="cleaned",
                                  showlegend=(i == 1)), row=i, col=1)
    fig.update_layout(height=200 * len(sensors.ids), margin=dict(t=70),
                       legend=HORIZONTAL_LEGEND)
    plot(fig)

    st.write("**All sensors - distribution shift**")
    fig = make_subplots(rows=1, cols=len(sensors.ids), subplot_titles=[sensors.label[s] for s in sensors.ids])
    for i, s in enumerate(sensors.ids, start=1):
        raw_vals = r["reg_long"].loc[r["reg_long"]["sensor_id"] == s, "value_raw"].dropna()
        clean_vals = r["production_wide"][s].dropna()
        fig.add_trace(go.Box(y=raw_vals, name="raw", fillcolor=_rgba(REFERENCE_LINE_COLOR, 0.25),
                              line=dict(color=REFERENCE_LINE_COLOR), marker=dict(color=REFERENCE_LINE_COLOR),
                              legendgroup="raw", showlegend=(i == 1)), row=1, col=i)
        fig.add_trace(go.Box(y=clean_vals, name="cleaned", fillcolor=_rgba(sensors.color[s], 0.25),
                              line=dict(color=sensors.color[s]), marker=dict(color=sensors.color[s]),
                              legendgroup="cleaned", showlegend=(i == 1)), row=1, col=i)
    fig.update_layout(height=400, margin=dict(t=70),
                       legend={**HORIZONTAL_LEGEND, "y": 1.08})
    plot(fig)

    st.subheader(":material/bar_chart: Aggregation - interactive overlay", divider="gray")
    st.caption("Per-sensor summary stats over a chosen period, computed on the cleaned+gap-filled series. "
               "Pick the period and which sensors/statistics to include - everything overlays on a single chart "
               "so series and stats are directly comparable.")

    a1, a2, a3 = st.columns([1, 2, 2])
    with a1:
        analysis_freq_label = st.selectbox(
            "Aggregation period", list(ANALYSIS_AGG_OPTIONS), index=1,
            key="analysis_agg_freq")
    with a2:
        analysis_sensors = st.multiselect("Sensors to overlay", sensors.ids, default=sensors.ids, key="analysis_agg_sensors")
    with a3:
        analysis_stats_labels = st.multiselect("Statistics to overlay", list(STAT_OPTIONS),
                                                 default=["Mean", "Minimum", "Maximum"], key="analysis_agg_stats")

    analysis_agg = P.aggregate(r["production"], ANALYSIS_AGG_OPTIONS[analysis_freq_label])
    analysis_stats = [STAT_OPTIONS[l] for l in analysis_stats_labels]

    if not analysis_sensors or not analysis_stats:
        st.info("Pick at least one sensor and one statistic to plot.")
    else:
        fig = go.Figure()
        for s in analysis_sensors:
            sub = analysis_agg[analysis_agg["sensor_id"] == s]
            for stat in analysis_stats:
                fig.add_trace(go.Scatter(x=sub["period"], y=sub[stat], mode="lines+markers",
                                          line=dict(color=sensors.color[s], dash=STAT_DASH[stat], width=2),
                                          marker=dict(size=4),
                                          name=f"{sensors.label[s]} - {stat}", legendgroup=s))
        fig.update_layout(height=480, margin=dict(t=20), legend=HORIZONTAL_LEGEND,
                           xaxis_title=f"{analysis_freq_label.lower()} period", yaxis_title="value")
        plot(fig)

    agg_display = analysis_agg.copy()
    agg_display[["mean", "min", "max", "std"]] = agg_display[["mean", "min", "max", "std"]].round(2)
    st.dataframe(agg_display, width='stretch', height=280)

    st.download_button("Download aggregated CSV", to_csv_bytes(analysis_agg, index=False),
                        file_name=f"sensors_agg_{ANALYSIS_AGG_OPTIONS[analysis_freq_label]}.csv",
                        mime="text/csv", icon=":material/download:")

    st.subheader(f":material/show_chart: Smoothing ({smooth_method}, window={smooth_window} steps)", divider="gray")
    st.caption("Rolling smoothing layered over the cleaned series - shown alongside it, not replacing it, so the "
               "underlying QC'd data stays available. Method/window in the sidebar.")

    st.write("**All sensors - smoothed**")
    fig = facet_grid([sensors.label[s] for s in sensors.ids])
    for i, s in enumerate(sensors.ids, start=1):
        sub = r["smoothed_wide"][s]
        add_area_trace(fig, sub.index, sub.values, sensors.color[s], row=i, col=1)
    fig.update_layout(height=200 * len(sensors.ids), margin=dict(t=40))
    plot(fig)
