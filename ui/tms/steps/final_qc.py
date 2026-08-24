"""Step 6: Final QC - corrected Signal, VWC and temperature channels
inspected together (cross-channel), on top of the per-channel initial QC
from step 3. The raw record stays untouched; invalid processed values are
flagged and set to NA in the _final columns only."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from ui.charts import diff_mask, facet_grid_before_after, plot, run_edges
from ui.generic.data_source import SensorMeta
from ui.fullscreen import is_fullscreen
from ui.theme import HORIZONTAL_LEGEND, REFERENCE_LINE_COLOR, TMS_FINAL_QC_COLORS, TMS_FINAL_QC_LABELS, TMS_FINAL_QC_PRIORITY

PANELS = ["Corrected Signal", "VWC", "T1", "T2", "T3"]
VALUE_COLS = ["signal_corrected", "vwc", "t1_raw", "t2_raw", "t3_raw"]
FLAGGABLE_COLS = {"signal_corrected", "vwc"}  # only the two derived-cross-channel series carry method markers
_SECTION = "tms_final_qc"


def render(r: dict, sensors: SensorMeta) -> None:
    final = r["final"]
    fullscreen = is_fullscreen(_SECTION)

    if not fullscreen:
        st.subheader("Final QC - flag counts", divider="gray")
        cols = st.columns(len(TMS_FINAL_QC_PRIORITY) + 1)
        cols[0].metric("Total flagged", int(final["is_final_qc"].sum()))
        for c, m in zip(cols[1:], TMS_FINAL_QC_PRIORITY):
            c.metric(TMS_FINAL_QC_LABELS[m], int(final[f"is_final_qc_{m}"].sum()))

    st.write("**Detail view - corrected Signal, VWC, T1/T2/T3 together**")
    sensor = st.selectbox("Sensor", sensors.ids, format_func=lambda s: sensors.label[s])
    sub = final[final["sensor_id"] == sensor].sort_values("timestamp").copy()

    sub["_method"] = None
    for m in TMS_FINAL_QC_PRIORITY:
        mask = sub[f"is_final_qc_{m}"].fillna(False) & sub["_method"].isna()
        sub.loc[mask, "_method"] = m

    # T1/T2/T3 are never touched by final QC (only the two derived cross-channel
    # series are) - so their before/after panels are always identical. Corrected
    # Signal/VWC's "after" panel only differs (with a real gap where final QC
    # excluded a point) when this sensor actually has a difference there.
    fig = facet_grid_before_after(PANELS)
    seen_methods = set()
    for i, (title, col) in enumerate(zip(PANELS, VALUE_COLS), start=1):
        after_col = f"{col}_final" if col in FLAGGABLE_COLS else col
        changed = diff_mask(sub[col], sub[after_col]) if col in FLAGGABLE_COLS else None

        fig.add_trace(go.Scatter(x=sub["timestamp"], y=sub[col], mode="lines", connectgaps=True,
                                  line=dict(color=REFERENCE_LINE_COLOR), showlegend=False), row=i, col=1)
        fig.add_trace(go.Scatter(x=sub["timestamp"], y=sub[after_col], mode="lines",
                                  connectgaps=(col not in FLAGGABLE_COLS),
                                  line=dict(color=REFERENCE_LINE_COLOR), showlegend=False), row=i, col=2)
        if changed is None or not changed.any():
            continue

        for m in TMS_FINAL_QC_PRIORITY:
            # run_edges, not the raw mask: a flatline run can flag hundreds of
            # consecutive points, which would otherwise draw one marker per
            # point and smear into a solid blob - marking just where each
            # flagged run starts/ends keeps isolated flags (the common case
            # for range/freezing/field-event) fully marked either way.
            out = sub[run_edges((sub["_method"] == m) & changed)]
            if len(out):
                fig.add_trace(go.Scatter(x=out["timestamp"], y=out[col], mode="markers",
                                          marker=dict(color=TMS_FINAL_QC_COLORS[m], size=8, line=dict(width=1, color="white")),
                                          name=TMS_FINAL_QC_LABELS[m], legendgroup=m, showlegend=(m not in seen_methods)), row=i, col=1)
                seen_methods.add(m)
    fig.update_layout(height=200 * len(PANELS), margin=dict(t=90), legend=HORIZONTAL_LEGEND)
    plot(fig)
