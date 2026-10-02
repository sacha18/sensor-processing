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

import numpy as np
import pandas as pd

from .. import store

_QUERY = """
SELECT r.__row_id AS __row_id,
       EXISTS (
           SELECT 1 FROM ev
           WHERE (
               ev.sensor_id IS NULL OR lower(trim(CAST(ev.sensor_id AS VARCHAR))) IN ('*', 'all', '')
               OR CAST(r.sensor_id AS VARCHAR) = CAST(ev.sensor_id AS VARCHAR)
           )
           AND (
               ev.treatment IS NULL OR lower(trim(CAST(ev.treatment AS VARCHAR))) IN ('*', 'all', '')
               OR CAST(r.treatment AS VARCHAR) = CAST(ev.treatment AS VARCHAR)
           )
           AND (ev."start" IS NULL OR r.timestamp >= ev."start")
           AND (ev."end" IS NULL OR r.timestamp <= ev."end")
       ) AS flag
FROM r
ORDER BY r.__row_id
"""


def field_event_flags(out: pd.DataFrame, channel: str, field_events: pd.DataFrame) -> pd.Series:
    if field_events is None or field_events.empty:
        return pd.Series(False, index=out.index)
    ev = field_events[field_events["channel"].isin([channel, "all"])]
    if ev.empty:
        return pd.Series(False, index=out.index)

    r = out[["sensor_id", "treatment", "timestamp"]].reset_index(drop=True).copy()
    r["__row_id"] = np.arange(len(r))
    result = store.sql_df(_QUERY, {"r": r, "ev": ev})
    result = result.sort_values("__row_id")
    return pd.Series(result["flag"].to_numpy(dtype=bool), index=out.index)
