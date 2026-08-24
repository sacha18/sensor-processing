"""Step 2: Deduplication - duplicate (sensor, timestamp) report."""
from __future__ import annotations

import streamlit as st

from ui.format import render_capped_dataframe, to_csv_bytes_cached


def render(r: dict) -> None:
    st.subheader("Duplicate sensor_id + timestamp pairs", divider="gray")
    dup = r["dup_report"]
    if dup.empty:
        st.success("No duplicate (sensor_id, timestamp) pairs found - value agreement was also checked, nothing to flag.")
    else:
        n_conflicting = int(dup["conflicting"].sum())
        st.warning(f"{len(dup)} duplicate (sensor, timestamp) pairs - keeping the most recent observation (max observation_id).")
        if n_conflicting:
            st.error(f"{n_conflicting} of these are conflicting: the repeated rows disagree on value_raw, not just a harmless re-send.")
        render_capped_dataframe(dup.sort_values("conflicting", ascending=False), width='stretch')
        st.download_button("Download duplicate pairs report CSV", to_csv_bytes_cached(dup, index=False),
                            file_name="duplicate_pairs_report.csv", mime="text/csv", icon=":material/download:")
    st.caption(f"Rows before: {len(r['raw_long'])} -> after deduplication: {len(r['deduped'])}")
