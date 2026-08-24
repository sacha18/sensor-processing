"""Shared row-matching helper for the correction (step 4) and calibration
(step 5) parameter tables: a params-table row applies to a reading if its
key matches either the sensor's own id or its metadata group_key, and (if
set) the reading's timestamp falls in [valid_from, valid_to]. A wildcard key
("*", "all", or blank) applies to every sensor - e.g. TOMST's own published
calibration is one universal equation, not one per sensor, so a single
sensor_id="*" row covers that case without requiring every sensor to share
a group_key.
"""
from __future__ import annotations

import pandas as pd

WILDCARD_KEYS = {"*", "all", ""}


def match_mask(df: pd.DataFrame, param_row: pd.Series) -> pd.Series:
    key = str(param_row["sensor_id"]).strip()
    if key.lower() in WILDCARD_KEYS or pd.isna(param_row["sensor_id"]):
        mask = pd.Series(True, index=df.index)
    else:
        mask = df["sensor_id"].astype(str) == key
        if "group_key" in df.columns:
            mask |= df["group_key"].astype(str) == key
    if pd.notna(param_row.get("valid_from")):
        mask &= df["timestamp"] >= param_row["valid_from"]
    if pd.notna(param_row.get("valid_to")):
        mask &= df["timestamp"] <= param_row["valid_to"]
    return mask
