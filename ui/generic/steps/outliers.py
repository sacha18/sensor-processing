"""Step 4 (part 1/2): Outlier detection - multi-method overview and per-sensor detail.

Rendered above ui.steps.manual_validation on the combined "Outliers" step, so
detection and review live on the same screen. Gated (ui.step_validate,
_SECTION below) like ui/tms/steps/*: ui.stepper's Next opens the before/after
at the bottom of this render() in fullscreen (ui.fullscreen) instead of
advancing straight away, matching the TMS steps' Next -> review -> Validate
flow rather than the free-advance every other generic step has.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from ui.charts import decimate, facet_grid, facet_grid_before_after, plot
from ui.fullscreen import is_fullscreen
from ui.format import render_capped_dataframe
from ui.generic.data_source import SensorMeta
from ui.theme import HORIZONTAL_LEGEND, METHOD_COLORS, METHOD_LABELS, METHOD_PRIORITY, REFERENCE_LINE_COLOR

_SECTION = "outliers"


def render(r: dict, sensors: SensorMeta, use_donor_regression: bool) -> None:
    fullscreen = is_fullscreen(_SECTION)

    qc = r["qc_long"].copy()
    qc["outlier_method"] = None
    for m in METHOD_PRIORITY:
        mask = qc[f"is_outlier_{m}"] & qc["outlier_method"].isna()
        qc.loc[mask, "outlier_method"] = m

    out_rows = qc[qc["is_outlier"]]

    if not fullscreen:
        st.subheader("Outlier detection (multiple methods)", divider="gray")
        st.caption("Colors below show which method caught each point (when several agree, priority is spike > "
                   "flatline > extreme value > rate-of-change).")

        cols = st.columns(5)
        cols[0].metric("Total outliers", len(out_rows))
        for c, m in zip(cols[1:], METHOD_PRIORITY):
            c.metric(METHOD_LABELS[m], int(qc[f"is_outlier_{m}"].sum()))

        if len(out_rows):
            render_capped_dataframe(out_rows[["sensor_id", "timestamp", "value_raw", "outlier_method"]], width='stretch')

        healed = out_rows.merge(r["production"][["sensor_id", "timestamp", "fill_method"]],
                                 on=["sensor_id", "timestamp"], how="left")
        n_healed = int((healed["fill_method"] == "outlier_donor_regression").sum())
        if use_donor_regression:
            st.caption(f"**Imputation via correlated time series**: {n_healed}/{len(out_rows)} outliers above were replaced "
                       "straight away by regression against their most correlated sensor (donor) rather than plain "
                       "interpolation - see the **Gap filling** step for the filled values, and its parameters "
                       "to tune the minimum correlation required.")
        else:
            st.caption("Imputation via correlated time series is currently **off** (see the **Gap filling** step's "
                       "parameters) - outliers below are left for plain interpolation instead.")

        st.write("**All sensors - raw with outliers**")
        fig = facet_grid([sensors.label[s] for s in sensors.ids])
        seen_methods = set()
        for i, s in enumerate(sensors.ids, start=1):
            sub = qc[qc["sensor_id"] == s].sort_values("timestamp")
            # decimated only for the line trace - the per-point method
            # markers below still need the full-resolution `sub` to flag
            # every matching point, not a stride-sampled approximation.
            line_sub = decimate(sub)
            fig.add_trace(go.Scatter(x=line_sub["timestamp"], y=line_sub["value_raw"], mode="lines", connectgaps=True,
                                      line=dict(color=REFERENCE_LINE_COLOR), showlegend=False), row=i, col=1)
            for m in METHOD_PRIORITY:
                out = sub[sub["outlier_method"] == m]
                if len(out):
                    fig.add_trace(go.Scatter(x=out["timestamp"], y=out["value_raw"], mode="markers",
                                              marker=dict(color=METHOD_COLORS[m], size=9, line=dict(width=1, color="white")),
                                              name=METHOD_LABELS[m], legendgroup=m, showlegend=(m not in seen_methods)), row=i, col=1)
                    seen_methods.add(m)
        fig.update_layout(height=230 * len(sensors.ids), margin=dict(t=70),
                           legend=HORIZONTAL_LEGEND)
        plot(fig)

    # Review content for the step gate - shown in both normal and fullscreen
    # layout (fullscreen just hides everything above via `if not fullscreen`),
    # same "always rendered, chrome hidden around it" shape as
    # ui/generic/steps/gapfill.py and every gated ui/tms/steps/* module.
    st.write("**Before / after - raw vs. outliers removed**")
    fig = facet_grid_before_after([sensors.label[s] for s in sensors.ids])
    for i, s in enumerate(sensors.ids, start=1):
        sub = decimate(qc[qc["sensor_id"] == s].sort_values("timestamp"))
        fig.add_trace(go.Scatter(x=sub["timestamp"], y=sub["value_raw"], mode="lines", connectgaps=True,
                                  line=dict(color=REFERENCE_LINE_COLOR), showlegend=False), row=i, col=1)
        fig.add_trace(go.Scatter(x=sub["timestamp"], y=sub["value_qc"], mode="lines",
                                  line=dict(color=sensors.color[s]), showlegend=False), row=i, col=2)
    fig.update_layout(height=230 * len(sensors.ids), margin=dict(t=90), legend=HORIZONTAL_LEGEND)
    plot(fig)
