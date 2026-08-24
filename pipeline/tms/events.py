"""Shared field-event flagging for initial QC (step 3, raw channels) and
final QC (step 6, corrected Signal/VWC) - both flag against the same
manually-logged event table (see ui/tms/config.py's "field_events" schema),
just for a different channel. An event's sensor_id and/or treatment can be
left blank/"*"/"all" to apply to every sensor, or every sensor of that
treatment - real deployments need blanket rules like "everything before the
stabilization date" or "every Crop field sensor during the harvest window",
not just single-sensor exclusions.
"""
from __future__ import annotations

import pandas as pd

from .params import WILDCARD_KEYS


def _is_wildcard(value) -> bool:
    return pd.isna(value) or str(value).strip().lower() in WILDCARD_KEYS


def field_event_flags(out: pd.DataFrame, channel: str, field_events: pd.DataFrame) -> pd.Series:
    flags = pd.Series(False, index=out.index)
    if field_events is None or field_events.empty:
        return flags
    ev = field_events[field_events["channel"].isin([channel, "all"])]
    for _, row in ev.iterrows():
        mask = pd.Series(True, index=out.index)
        if not _is_wildcard(row.get("sensor_id")):
            mask &= out["sensor_id"].astype(str) == str(row["sensor_id"])
        if "treatment" in ev.columns and not _is_wildcard(row.get("treatment")):
            mask &= out["treatment"].astype(str) == str(row["treatment"])
        if pd.notna(row.get("start")):
            mask &= out["timestamp"] >= row["start"]
        if pd.notna(row.get("end")):
            mask &= out["timestamp"] <= row["end"]
        flags |= mask
    return flags
