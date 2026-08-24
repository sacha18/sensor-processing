"""Step 3: Initial QC - inspect T1/T2/T3 and raw Signal, independently per
channel (a problem on one channel doesn't flag the others). Below the chart,
known field events can be logged manually and feed back into the flags."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from pipeline.tms.config import SIGNAL_CHANNELS
from ui.charts import facet_grid, plot
from ui.generic.data_source import SensorMeta
from ui.theme import HORIZONTAL_LEGEND, REFERENCE_LINE_COLOR, TMS_QC_COLORS, TMS_QC_LABELS, TMS_QC_PRIORITY
from ui.tms.config import editor_key, get_table, merge_uploaded, set_table

CHANNEL_TITLES = {"t1": "T1", "t2": "T2", "t3": "T3", "signal": "Signal (raw)"}


def render(r: dict, sensors: SensorMeta) -> None:
    qc = r["qc"]

    st.subheader("Initial QC - flag counts per channel", divider="gray")
    cols = st.columns(len(SIGNAL_CHANNELS))
    for c, ch in zip(cols, SIGNAL_CHANNELS):
        c.metric(CHANNEL_TITLES[ch], int(qc[f"is_qc_{ch}"].sum()))

    st.write("**Detail view**")
    sensor = st.selectbox("Sensor", sensors.ids, format_func=lambda s: sensors.label[s])
    sub = qc[qc["sensor_id"] == sensor].sort_values("timestamp").copy()

    fig = facet_grid([CHANNEL_TITLES[ch] for ch in SIGNAL_CHANNELS])
    seen_methods = set()
    for i, ch in enumerate(SIGNAL_CHANNELS, start=1):
        col = f"{ch}_raw"
        fig.add_trace(go.Scatter(x=sub["timestamp"], y=sub[col], mode="lines", connectgaps=True,
                                  line=dict(color=REFERENCE_LINE_COLOR), showlegend=False), row=i, col=1)

        method_col = f"_method_{ch}"
        sub[method_col] = None
        for m in TMS_QC_PRIORITY:
            flag_col = f"is_qc_{m}_{ch}"
            if flag_col not in sub.columns:
                continue
            mask = sub[flag_col].fillna(False) & sub[method_col].isna()
            sub.loc[mask, method_col] = m

        for m in TMS_QC_PRIORITY:
            out = sub[sub[method_col] == m]
            if len(out):
                fig.add_trace(go.Scatter(x=out["timestamp"], y=out[col], mode="markers",
                                          marker=dict(color=TMS_QC_COLORS[m], size=8, line=dict(width=1, color="white")),
                                          name=TMS_QC_LABELS[m], legendgroup=m, showlegend=(m not in seen_methods)), row=i, col=1)
                seen_methods.add(m)
    fig.update_layout(height=200 * len(SIGNAL_CHANNELS), margin=dict(t=70), legend=HORIZONTAL_LEGEND)
    plot(fig)

    _render_field_events()


def _render_field_events() -> None:
    st.subheader("Known field events", divider="gray")

    uploaded = st.file_uploader(
        "Upload field events CSV/JSON", type=["csv", "json"], key="tms_field_events_upload",
        help="Manually logged events (maintenance visit, vegetation cut, animal disturbance, harvest, "
             "stabilization period, ...) that flag a channel over a date range, regardless of what the automatic "
             "methods above catch. Channel = vwc flags the final calibrated series instead of a raw channel (see "
             "Final QC); all covers every raw channel. Leave Sensor and/or Treatment blank (or \"*\") for a "
             "blanket rule - e.g. every sensor before a stabilization date, or every sensor of one treatment "
             "during a harvest window.")
    if uploaded is not None and st.session_state.get("tms_field_events_upload_name") != uploaded.name:
        n = merge_uploaded("field_events", uploaded)
        st.session_state["tms_field_events_upload_name"] = uploaded.name
        st.success(f"Added {n} row(s) from {uploaded.name}.")
        st.rerun()

    edited = st.data_editor(
        get_table("field_events"), num_rows="dynamic", width='stretch', key=editor_key("field_events"),
        column_config={
            "sensor_id": st.column_config.TextColumn("Sensor", help="Blank or \"*\" = every sensor."),
            "treatment": st.column_config.TextColumn("Treatment", help="Blank or \"*\" = every treatment. Must match the metadata Treatment column."),
            "channel": st.column_config.SelectboxColumn("Channel", options=["all", "t1", "t2", "t3", "signal", "vwc"], required=True),
            "start": st.column_config.DatetimeColumn("Start", required=True),
            "end": st.column_config.DatetimeColumn("End", help="Blank = ongoing."),
        },
    )
    if st.button("Apply field events", type="primary", icon=":material/check_circle:"):
        set_table("field_events", edited)
        st.rerun()
