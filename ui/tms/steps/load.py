"""Step 1: Loading, merge & continuity - downloads grouped by sensor,
overlaps merged (latest download wins), duplicates removed, gaps reported
but never auto-filled at this stage."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from ui.charts import plot
from ui.generic.data_source import SensorMeta
from ui.format import render_capped_dataframe, to_csv_bytes, to_csv_bytes_cached
from ui.theme import COLORS, HORIZONTAL_LEGEND


def render(r: dict, sensors: SensorMeta) -> None:
    raw = r["raw_wide"]
    merged = r["merged"]

    st.subheader("Files loaded", divider="gray")
    file_summary = raw.groupby(["sensor_id", "source_file"]).agg(
        n=("timestamp", "size"), start=("timestamp", "min"), end=("timestamp", "max"),
    ).reset_index()
    st.dataframe(file_summary, width='stretch')

    st.subheader("Merge & deduplication", divider="gray")
    dup = r["dup_report"]
    if dup.empty:
        st.success("No duplicate (sensor, timestamp) pairs across downloads - value agreement was also checked.")
    else:
        n_conflicting = int(dup["conflicting"].sum())
        st.warning(f"{len(dup)} duplicate (sensor, timestamp) pairs across downloads - keeping the most recently "
                   "downloaded file's row for each (a re-download is a superset re-read of the logger's memory).")
        if n_conflicting:
            st.error(f"{n_conflicting} of these are conflicting: the repeated rows disagree on a value, not just "
                     "a harmless re-download.")
        render_capped_dataframe(dup.sort_values("conflicting", ascending=False), width='stretch')
        st.download_button("Download duplicate pairs report CSV", to_csv_bytes_cached(dup, index=False),
                            file_name="tms_duplicate_pairs_report.csv", mime="text/csv",
                            icon=":material/download:")
    st.caption(f"Rows before: {len(raw)} -> after merge/dedup: {len(merged)}")
    st.download_button("Download merged raw archive CSV (all raw fields + source_file)",
                        to_csv_bytes_cached(merged, index=False), file_name="tms_merged_raw_archive.csv",
                        mime="text/csv", icon=":material/download:",
                        help="Every raw field as parsed (including the ones unused downstream), one row per "
                             "sensor/timestamp after merge/dedup, with which source file each row came from.")

    st.subheader("Continuity - gap report", divider="gray")
    st.caption("Gaps are reported only - never auto-filled at this stage.")
    gaps = r["gap_report"]
    if gaps.empty:
        st.success("No gaps detected beyond the expected sampling step.")
    else:
        cols = st.columns(3)
        cols[0].metric("Gaps", len(gaps))
        cols[1].metric("Missing steps (total)", int(gaps["n_missing_steps"].sum()))
        cols[2].metric("Longest gap", str(gaps["gap_duration"].max()))
        st.dataframe(gaps, width='stretch')
        st.download_button("Download gap report CSV", to_csv_bytes(gaps, index=False),
                            file_name="tms_gap_report.csv", mime="text/csv", icon=":material/download:")

    st.write("**Per-sensor timeline - observed readings**")
    fig = go.Figure()
    for i, s in enumerate(sensors.ids):
        sub = merged[merged["sensor_id"] == s].sort_values("timestamp")
        # Scattergl (WebGL), not Scatter (SVG) - a large multi-hundred-file
        # upload can put tens of millions of points on this chart across all
        # sensors combined, which an SVG-based trace renders as one DOM
        # element per marker and chokes the browser on.
        fig.add_trace(go.Scattergl(x=sub["timestamp"], y=[sensors.label[s]] * len(sub), mode="markers",
                                    marker=dict(symbol="line-ns", line=dict(width=2, color=COLORS["observed"]), size=9),
                                    name="observed", legendgroup="observed", showlegend=(i == 0), hoverinfo="x"))
    fig.update_layout(height=70 + 36 * len(sensors.ids), margin=dict(t=30), legend=HORIZONTAL_LEGEND)
    plot(fig)
