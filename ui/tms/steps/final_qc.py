"""Step 6: Final QC - corrected Signal, VWC and temperature channels
inspected together (cross-channel), on top of the per-channel initial QC
from step 3. The raw record stays untouched; invalid processed values are
flagged and set to NA in the _final columns only.

Also hosts the interactive multi-sensor inspection chart and the manual QC
editor - both operate on this step's `final` frame since it's the first
point in the pipeline where raw Signal, corrected Signal/VWC and T1/T2/T3
are all available together. A manual edit is just a field event (see
pipeline/tms/events.py) written with an audit stamp (edit_id/created_by/
created_at - see ui/tms/config.py's field_events schema) - it flows back
through the existing field-event flag on the next pipeline run exactly like
a bulk-uploaded one, no separate enforcement path needed.
"""
from __future__ import annotations

import uuid

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui.charts import add_flag_shading, decimate, diff_mask, facet_grid, facet_grid_before_after, plot, run_edges
from ui.generic.data_source import SensorMeta
from ui.fullscreen import is_fullscreen
from ui.theme import (CHANGED_HIGHLIGHT_COLOR, HORIZONTAL_LEGEND, REFERENCE_LINE_COLOR, TMS_FINAL_QC_COLORS,
                       TMS_FINAL_QC_LABELS, TMS_FINAL_QC_PRIORITY)
from ui.tms.config import delete_row, get_table, set_table

PANELS = ["Corrected Signal", "VWC", "T1", "T2", "T3"]
VALUE_COLS = ["signal_corrected", "vwc", "t1_raw", "t2_raw", "t3_raw"]
FLAGGABLE_COLS = {"signal_corrected", "vwc"}  # only the two derived-cross-channel series carry method markers
# background-shading flag per panel - Corrected Signal/VWC are excluded by final
# QC's own flag; T1/T2/T3 are never touched by final QC (see render()'s comment
# below) but are still shaded by their own upstream Initial QC flag, so "this
# channel was already excluded before final QC" is visible on this chart too.
PANEL_FLAG_COLS = {"signal_corrected": "is_final_qc", "vwc": "is_final_qc",
                    "t1_raw": "is_qc_t1", "t2_raw": "is_qc_t2", "t3_raw": "is_qc_t3"}
_SECTION = "tms_final_qc"

# Interactive inspection includes raw Signal alongside the corrected/derived
# series (the before/after chart above doesn't) so a suspicious corrected
# value can be checked straight against the raw reading it came from.
INSPECT_PANELS = ["Raw Signal", "Corrected Signal", "VWC", "T1", "T2", "T3"]
INSPECT_COLS = ["signal_raw", "signal_corrected", "vwc", "t1_raw", "t2_raw", "t3_raw"]
INSPECT_FLAG_COLS = ["is_qc_signal", "is_final_qc", "is_final_qc", "is_qc_t1", "is_qc_t2", "is_qc_t3"]

# channel code (written straight to the field_events table) -> readable label.
# "all" is what "whole sensor" means in practice: field_event_flags is folded
# into every raw channel's flag (initial QC) *and* vwc's (final QC) whenever a
# row's channel is "all" - see pipeline/tms/events.py.
MANUAL_QC_CHANNELS = [
    ("vwc", "Moisture (VWC)"), ("t1", "T1 (temperature)"), ("t2", "T2 (temperature)"),
    ("t3", "T3 (temperature)"), ("signal", "Signal (raw)"), ("all", "Whole sensor (all channels)"),
]


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

        # shading must follow each panel's first trace - plotly's
        # add_vrect(row=, col=) silently drops the shape otherwise (no axis
        # reference to resolve it against yet).
        fig.add_trace(go.Scatter(x=sub["timestamp"], y=sub[col], mode="lines", connectgaps=True,
                                  line=dict(color=REFERENCE_LINE_COLOR), showlegend=False), row=i, col=1)
        fig.add_trace(go.Scatter(x=sub["timestamp"], y=sub[after_col], mode="lines",
                                  connectgaps=(col not in FLAGGABLE_COLS),
                                  line=dict(color=REFERENCE_LINE_COLOR), showlegend=False), row=i, col=2)
        add_flag_shading(fig, sub["timestamp"], sub[PANEL_FLAG_COLS[col]], CHANGED_HIGHLIGHT_COLOR, row=i, col=1)
        add_flag_shading(fig, sub["timestamp"], sub[PANEL_FLAG_COLS[col]], CHANGED_HIGHLIGHT_COLOR, row=i, col=2)
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

    if not fullscreen:
        _render_inspection(final, sensors)
        _render_manual_qc(final, sensors)


def _render_inspection(final: pd.DataFrame, sensors: SensorMeta) -> None:
    st.subheader("Interactive inspection", divider="gray")
    st.caption("Compare one or more sensors side by side - raw Signal, corrected Signal/VWC and T1/T2/T3 all "
               "share the same time window. Drag the range slider under the bottom panel to zoom into a stretch. "
               "Shaded red bands mark a period excluded for that channel - by an automatic QC method, a known "
               "field event, or a manual edit below - regardless of which one did it.")
    selected = st.multiselect("Sensor(s)", sensors.ids, default=sensors.ids[:1],
                               format_func=lambda s: sensors.label[s], key="tms_inspect_sensors")
    if not selected:
        st.info("Pick at least one sensor to inspect.")
        return

    fig = facet_grid(INSPECT_PANELS)
    for sid in selected:
        sub = decimate(final[final["sensor_id"] == sid].sort_values("timestamp"))
        color = sensors.color[sid]
        for i, (col, flag_col) in enumerate(zip(INSPECT_COLS, INSPECT_FLAG_COLS), start=1):
            # shading must follow this row/col's first trace - plotly's
            # add_vrect(row=, col=) silently drops the shape otherwise (no
            # axis reference to resolve it against yet).
            fig.add_trace(go.Scatter(x=sub["timestamp"], y=sub[col], mode="lines", connectgaps=True,
                                      line=dict(color=color), name=sensors.label[sid], legendgroup=sid,
                                      showlegend=(i == 1)), row=i, col=1)
            add_flag_shading(fig, sub["timestamp"], sub[flag_col], CHANGED_HIGHLIGHT_COLOR, row=i, col=1)
    fig.update_xaxes(rangeslider=dict(visible=True), row=len(INSPECT_PANELS), col=1)
    fig.update_layout(height=190 * len(INSPECT_PANELS) + 60, margin=dict(t=70), legend=HORIZONTAL_LEGEND)
    plot(fig)


def _selection_chart(sub: pd.DataFrame, sensor: str, sensors: SensorMeta):
    """VWC time series with Plotly's box-select enabled (dragmode="select") -
    dragging a box across the chart returns its x-range below, prefilling
    the interval form so a bad-looking stretch can be marked invalid without
    typing timestamps by hand (they can still be typed/adjusted directly -
    the form is the source of truth, this is just a shortcut into it). A
    range slider gives the same zoom/inspect ability as the read-only charts
    above; it works independently of dragmode, so both stay usable together.
    Already-excluded periods (from any source - automatic QC, a known field
    event, an earlier manual edit) are shaded red, so submitting the form
    below and seeing a new red band appear here is the direct confirmation
    the edit actually took effect.
    """
    fig = go.Figure()
    add_flag_shading(fig, sub["timestamp"], sub["is_final_qc"], CHANGED_HIGHLIGHT_COLOR)
    fig.add_trace(go.Scatter(x=sub["timestamp"], y=sub["vwc"], mode="lines", connectgaps=True,
                              line=dict(color=sensors.color[sensor]), name="VWC", showlegend=False))
    fig.update_layout(height=280, margin=dict(t=30), dragmode="select",
                       xaxis=dict(rangeslider=dict(visible=True)), yaxis_title="VWC")
    event = st.plotly_chart(fig, key="tms_manual_qc_select", on_select="rerun",
                             selection_mode=["box"], config={"scrollZoom": False})
    boxes = event.selection.get("box") if event is not None else None
    if boxes:
        x0, x1 = boxes[0]["x"]
        return pd.to_datetime(x0), pd.to_datetime(x1)
    return None, None


def _manual_qc_rows(table: pd.DataFrame) -> pd.DataFrame:
    """Rows added through this editor, not a bulk CSV/JSON upload or the
    Known field events table (Initial QC step) - identified by having a
    created_by stamp, the one field only this form ever fills in."""
    return table[table["created_by"].notna()] if "created_by" in table.columns else table.iloc[0:0]


def _edit_summary(rows: pd.DataFrame) -> str:
    first = rows.iloc[0]
    channels = ", ".join(sorted(rows["channel"].astype(str).unique()))
    start, end = first["start"], first["end"]
    window = f"{start if pd.notna(start) else '...'} -> {end if pd.notna(end) else 'ongoing'}"
    note = str(first.get("note") or "").strip()
    note_part = f" - _{note}_" if note else ""
    return (f"`{first['sensor_id']}` - **{channels}** - {window}{note_part}  \n"
            f"by {first['created_by']} at {first['created_at']}")


def _render_manual_qc(final: pd.DataFrame, sensors: SensorMeta) -> None:
    st.subheader("Manual QC editing", divider="gray")
    st.caption("Drag a box across the chart below to pick a time interval (or pick one directly below), pick "
               "which channel(s) it invalidates, and give a reason. It's logged as a field event - same "
               "mechanism as \"Known field events\" on the Initial QC step - with your name and a timestamp, and "
               "feeds straight back into the flag counts above. Review or revert any edit at the bottom.")

    sensor = st.selectbox("Sensor", sensors.ids, format_func=lambda s: sensors.label[s], key="tms_manual_qc_sensor")
    sub = final[final["sensor_id"] == sensor].sort_values("timestamp")

    sel_start, sel_end = _selection_chart(sub, sensor, sensors)
    # keys the interval date inputs by the current box selection (same trick
    # as ui.tms.config.editor_key) - a new drag replaces their default value,
    # while adjusting the date/time within the same selection (same key) is
    # preserved instead of being overwritten by the same default every rerun.
    sel_token = f"{sel_start}_{sel_end}" if sel_start is not None else "none"

    reviewer = st.text_input("Your name / initials", value=st.session_state.get("tms_manual_qc_user", ""),
                              key="tms_manual_qc_user_input",
                              help="Remembered for the rest of the session - stamped on every edit you make below.")
    st.session_state["tms_manual_qc_user"] = reviewer

    with st.form("tms_manual_qc_add", clear_on_submit=True, border=True):
        st.write("**Mark an interval invalid**")
        c1, c2 = st.columns(2)
        start = c1.datetime_input("Start", value=sel_start, format="YYYY-MM-DD",
                                   key=f"tms_manual_qc_start_{sel_token}")
        end = c2.datetime_input("End", value=sel_end, format="YYYY-MM-DD", help="Blank = ongoing.",
                                 key=f"tms_manual_qc_end_{sel_token}")
        channel_labels = dict(MANUAL_QC_CHANNELS)
        channels = st.multiselect("Invalidate", [c for c, _ in MANUAL_QC_CHANNELS],
                                   format_func=lambda c: channel_labels[c],
                                   help="\"Whole sensor\" wins over anything else picked alongside it.")
        reason = st.text_input("Reason", placeholder="e.g. animal disturbance, maintenance visit, vegetation cut")

        if st.form_submit_button("Mark interval invalid", icon=":material/block:", type="primary"):
            if not reviewer.strip():
                st.error("Enter your name/initials above first - every manual edit is stamped with it.")
            elif not channels:
                st.error("Pick at least one channel to invalidate.")
            elif start is None:
                st.error("Start is required - drag a box on the chart above, or pick a date directly.")
            elif not reason.strip():
                st.error("A reason is required - it's logged alongside the edit for later review.")
            else:
                write_channels = ["all"] if "all" in channels else channels
                edit_id, now = str(uuid.uuid4()), pd.Timestamp.now()
                new_rows = pd.DataFrame([{
                    "sensor_id": sensor, "treatment": None, "channel": ch, "start": start, "end": end,
                    "event_type": "manual_exclusion", "note": reason.strip(),
                    "edit_id": edit_id, "created_by": reviewer.strip(), "created_at": now,
                } for ch in write_channels])
                set_table("field_events", pd.concat([get_table("field_events"), new_rows], ignore_index=True))
                st.success(f"Marked {sensor} invalid for {', '.join(channel_labels[c] for c in write_channels)} "
                           f"from {start} to {end if end is not None else 'ongoing'}.")
                st.rerun()

    manual_rows = _manual_qc_rows(get_table("field_events"))
    if manual_rows.empty:
        st.caption("No manual edits yet for this session.")
        return

    st.write(f"**{manual_rows['edit_id'].nunique()} manual edit(s)**")
    for eid, rows in manual_rows.groupby("edit_id", sort=False):
        rows = rows.sort_values("created_at")
        c1, c2 = st.columns([6, 1])
        c1.markdown(_edit_summary(rows))
        if c2.button("Revert", key=f"revert_manual_qc_{eid}", icon=":material/undo:"):
            delete_row("field_events", rows.index.tolist())
            st.rerun()
