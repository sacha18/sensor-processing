"""Step 1: Loading - raw data overview."""
from __future__ import annotations

import streamlit as st


def render(r: dict, units: dict) -> None:
    st.subheader("Raw data", divider="gray")
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
