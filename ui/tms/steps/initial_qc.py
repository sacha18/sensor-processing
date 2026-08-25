"""Step 3: Initial QC - inspect T1/T2/T3 and raw Signal, independently per
channel (a problem on one channel doesn't flag the others). Below the chart,
known field events can be logged manually and feed back into the flags."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from pipeline.tms.config import SIGNAL_CHANNELS
from ui.charts import add_flag_shading, facet_grid, plot
from ui.generic.data_source import SensorMeta
from ui.theme import (CHANGED_HIGHLIGHT_COLOR, HORIZONTAL_LEGEND, REFERENCE_LINE_COLOR, TMS_QC_COLORS,
                       TMS_QC_LABELS, TMS_QC_PRIORITY)
from ui.tms.config import delete_row, get_table, merge_uploaded, set_table

CHANNEL_TITLES = {"t1": "T1", "t2": "T2", "t3": "T3", "signal": "Signal (raw)"}
FIELD_EVENT_CHANNELS = ["all", "t1", "t2", "t3", "signal", "vwc"]


def render(r: dict, sensors: SensorMeta) -> None:
    qc = r["qc"]

    st.subheader("Initial QC - flag counts per channel", divider="gray")
    cols = st.columns(len(SIGNAL_CHANNELS))
    for c, ch in zip(cols, SIGNAL_CHANNELS):
        c.metric(CHANNEL_TITLES[ch], int(qc[f"is_qc_{ch}"].sum()))

    st.write("**Detail view** - shaded red bands mark a period excluded for that channel (any method - "
             "automatic QC, a known field event below, or a manual edit on the Final QC step).")
    sensor = st.selectbox("Sensor", sensors.ids, format_func=lambda s: sensors.label[s])
    sub = qc[qc["sensor_id"] == sensor].sort_values("timestamp").copy()

    fig = facet_grid([CHANNEL_TITLES[ch] for ch in SIGNAL_CHANNELS])
    seen_methods = set()
    for i, ch in enumerate(SIGNAL_CHANNELS, start=1):
        col = f"{ch}_raw"
        # shading must be added after this row/col's first trace - plotly's
        # add_vrect(row=, col=) silently drops the shape if that subplot
        # cell has no trace in it yet to resolve the axis reference against.
        fig.add_trace(go.Scatter(x=sub["timestamp"], y=sub[col], mode="lines", connectgaps=True,
                                  line=dict(color=REFERENCE_LINE_COLOR), showlegend=False), row=i, col=1)
        add_flag_shading(fig, sub["timestamp"], sub[f"is_qc_{ch}"], CHANGED_HIGHLIGHT_COLOR, row=i, col=1)

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

    _render_field_events(sensors)


def _clean(v, default=""):
    # pandas' default string dtype represents a missing value as a plain
    # float('nan') - truthy in Python, unlike None - so a bare `v or ...`/
    # `if v` check silently treats a missing cell as present. pd.isna()
    # catches it (and NaT/pd.NA/None) regardless of the column's dtype.
    return default if pd.isna(v) else v


def _sensor_group_options(sensors: SensorMeta) -> list[str]:
    groups = get_table("metadata")["group_key"].dropna().astype(str).str.strip()
    return ["*"] + sorted(set(sensors.ids) | {g for g in groups if g})


def _treatment_options() -> list[str]:
    treatments = get_table("metadata")["treatment"].dropna().astype(str).str.strip()
    return sorted({t for t in treatments if t})


def _event_summary(table: pd.DataFrame, i) -> str:
    """Reads each field with .at[] rather than a row Series from
    iterrows() - when every value in a row is missing, pandas can unify
    that row's dtype to datetime64 (picking a "common type" across its
    columns), turning even string columns like sensor_id into NaT. .at[]
    reads straight from each column's own array, unaffected by that."""
    sensor_id = _clean(table.at[i, "sensor_id"]) or "*"
    treatment = _clean(table.at[i, "treatment"])
    scope = f"`{sensor_id}`" + (f" / treatment `{treatment}`" if treatment else "")
    vf, vt = table.at[i, "start"], table.at[i, "end"]
    window = f"{vf if pd.notna(vf) else '...'} - {vt if pd.notna(vt) else 'ongoing'}"
    event_type = _clean(table.at[i, "event_type"])
    type_part = f" - _{event_type}_" if event_type else ""
    note = _clean(table.at[i, "note"])
    note_part = f" - {note}" if note else ""
    created_by = _clean(table.at[i, "created_by"])
    by_part = f"  \nadded manually by {created_by} at {table.at[i, 'created_at']}" if created_by else ""
    return f"{scope} - **{table.at[i, 'channel']}** - {window}{type_part}{note_part}{by_part}"


def _render_field_events(sensors: SensorMeta) -> None:
    st.subheader("Known field events", divider="gray")
    st.caption("Manually logged events (maintenance visit, vegetation cut, animal disturbance, harvest, "
               "stabilization period, ...) that flag a channel over a date range, regardless of what the "
               "automatic methods above catch. Channel = vwc flags the final calibrated series instead of a raw "
               "channel (see Final QC); all excludes every raw channel and vwc together (a whole-sensor "
               "exclusion).")

    uploaded = st.file_uploader(
        "Upload field events CSV/JSON", type=["csv", "json"], key="tms_field_events_upload",
        help="Same columns as the form below (sensor_id, treatment, channel, start, end, event_type, note) - "
             "useful for a big batch of events at once.")
    if uploaded is not None and st.session_state.get("tms_field_events_upload_name") != uploaded.name:
        n = merge_uploaded("field_events", uploaded)
        st.session_state["tms_field_events_upload_name"] = uploaded.name
        st.success(f"Added {n} row(s) from {uploaded.name}.")
        st.rerun()

    with st.form("tms_field_event_add", clear_on_submit=True, border=True):
        st.write("**Add a field event**")
        c1, c2, c3 = st.columns(3)
        sensor_id = c1.selectbox(
            "Sensor or group", _sensor_group_options(sensors), index=None, placeholder="*",
            accept_new_options=True, key="tms_field_event_add_sensor",
            help="Blank or \"*\" = every sensor. Pick a loaded sensor id or a metadata Group, or type a new one.")
        treatment = c2.selectbox(
            "Treatment", _treatment_options(), index=None, placeholder="every treatment",
            accept_new_options=True, key="tms_field_event_add_treatment",
            help="Blank = every treatment. Pick one from the metadata Treatment column, or type a new one.")
        channel = c3.selectbox("Channel", FIELD_EVENT_CHANNELS)
        c4, c5 = st.columns(2)
        start = c4.datetime_input("Start", value=None, format="YYYY-MM-DD")
        end = c5.datetime_input("End", value=None, format="YYYY-MM-DD", help="Blank = ongoing.")
        c6, c7 = st.columns(2)
        event_type = c6.text_input("Event type", placeholder="e.g. maintenance, harvest, vegetation cut")
        note = c7.text_input("Note")
        if st.form_submit_button("Add event", icon=":material/add_circle:", type="primary"):
            if start is None:
                st.error("Start is required.")
            else:
                new_row = pd.DataFrame([{
                    "sensor_id": (sensor_id or "").strip() or "*", "treatment": (treatment or "").strip() or None,
                    "channel": channel, "start": start, "end": end,
                    "event_type": event_type.strip() or None, "note": note.strip() or None,
                }])
                set_table("field_events", pd.concat([get_table("field_events"), new_row], ignore_index=True))
                st.rerun()

    table = get_table("field_events")
    if table.empty:
        st.caption("No field events yet - add one above, or upload a file.")
    else:
        st.write(f"**{len(table)} event(s)**")
        for i in table.index:
            c1, c2 = st.columns([6, 1])
            c1.markdown(_event_summary(table, i))
            if c2.button("Delete", key=f"del_field_event_{i}", icon=":material/delete:"):
                delete_row("field_events", i)
                st.rerun()
