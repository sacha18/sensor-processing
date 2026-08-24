"""Applies committed manual-validation overrides to the pipeline result.

Runs unconditionally on every rerun (not just while on the Outliers &
validation step) so every step below sees the committed values regardless
of which step is currently on screen.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import pipeline as P


def apply_manual_overrides(r: dict, smooth_window: int, smooth_method: str) -> int:
    st.session_state.setdefault("manual_overrides", {})
    if not st.session_state.manual_overrides:
        return 0

    ov_keys = list(st.session_state.manual_overrides.keys())
    ov_df = pd.DataFrame({
        "sensor_id": [k[0] for k in ov_keys],
        "timestamp": [k[1] for k in ov_keys],
        "override_value": [st.session_state.manual_overrides[k] for k in ov_keys],
        "validated": True,
    })
    prod = r["production"].merge(ov_df, on=["sensor_id", "timestamp"], how="left")
    eligible = prod["validated"].fillna(False) & (prod["fill_method"] != "observed")
    if eligible.any():
        prod.loc[eligible, "value_clean"] = prod.loc[eligible, "override_value"]
        prod.loc[eligible, "fill_method"] = "manual_validated"
    prod = prod.drop(columns=["override_value", "validated"])
    r["production"] = prod
    r["production_wide"] = prod.pivot(index="timestamp", columns="sensor_id", values="value_clean").sort_index()
    r["agg"] = P.aggregate(prod)
    r["smoothed_wide"] = P.smooth(r["production_wide"], smooth_window, smooth_method)
    return int(eligible.sum())
