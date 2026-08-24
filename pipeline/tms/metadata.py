"""Step 2: metadata assignment.

Deployment metadata (site, treatment, position, depth, install period, ...)
lives in its own table - one row per sensor per install period, since a
logger can be redeployed - rather than being hardcoded (see ui/tms/config.py
for how that table gets populated, by upload and/or manual edit). A reading
is matched to whichever metadata row's [install_start, install_end] window
contains its timestamp; readings matching no window are excluded from the
working series and reported separately, per spec.
"""
from __future__ import annotations

import pandas as pd

METADATA_COLUMNS = [
    "sensor_id", "group_key", "site", "treatment", "position", "position_depth",
    "row", "transect", "depth_cm", "t1_label", "t2_label", "t3_label",
    "install_start", "install_end", "notes",
]
_EXTRA_COLUMNS = [c for c in METADATA_COLUMNS if c != "sensor_id"]


def apply_metadata(merged: pd.DataFrame, metadata_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    matched_mask = pd.Series(False, index=merged.index)
    matched_parts = []

    if metadata_df is not None and not metadata_df.empty:
        for install_id, row in metadata_df.reset_index(drop=True).iterrows():
            mask = merged["sensor_id"].astype(str) == str(row["sensor_id"])
            if pd.notna(row.get("install_start")):
                mask &= merged["timestamp"] >= row["install_start"]
            if pd.notna(row.get("install_end")):
                mask &= merged["timestamp"] <= row["install_end"]
            if not mask.any():
                continue
            sub = merged.loc[mask].copy()
            for c in _EXTRA_COLUMNS:
                sub[c] = row.get(c)
            sub["install_id"] = install_id
            matched_parts.append(sub)
            matched_mask |= mask

    if matched_parts:
        with_metadata = pd.concat(matched_parts, ignore_index=True).sort_values(["sensor_id", "timestamp"]).reset_index(drop=True)
    else:
        with_metadata = merged.iloc[0:0].copy()
        for c in _EXTRA_COLUMNS:
            with_metadata[c] = pd.Series(dtype="object")
        with_metadata["install_id"] = pd.Series(dtype="int64")

    excluded = merged.loc[~matched_mask].copy()
    excluded["reason"] = "outside_install_period" if (metadata_df is not None and not metadata_df.empty) else "no_metadata_configured"

    return with_metadata, excluded.reset_index(drop=True)
