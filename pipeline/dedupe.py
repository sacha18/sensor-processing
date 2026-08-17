"""De-duplicate repeated (sensor, timestamp) observations.

Keeps the highest observation_id (most recent write) for any repeated
sensor/timestamp pair. The report flags which duplicate groups are
"conflicting" - i.e. the repeated rows don't even agree on value_raw, so
silently keeping the last write is discarding a real disagreement, not just
a harmless re-transmission.
"""
from __future__ import annotations

import pandas as pd


def dedupe(raw_long: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    dup_counts = raw_long.groupby(["sensor_id", "timestamp"]).size()
    dup_keys = dup_counts[dup_counts > 1].reset_index(name="n_dup")

    dup_report = dup_keys.merge(
        raw_long.groupby(["sensor_id", "timestamp"])["value_raw"].agg(
            n_distinct_values="nunique", value_min="min", value_max="max"
        ).reset_index(),
        on=["sensor_id", "timestamp"],
    )
    dup_report["value_spread"] = dup_report["value_max"] - dup_report["value_min"]
    dup_report["conflicting"] = dup_report["n_distinct_values"] > 1

    out = raw_long.copy()
    out["_obs_id_num"] = out["observation_id"].astype(int)
    out = (
        out.sort_values("_obs_id_num")
        .drop_duplicates(subset=["sensor_id", "timestamp"], keep="last")
        .drop(columns="_obs_id_num")
        .sort_values(["sensor_id", "timestamp"])
        .reset_index(drop=True)
    )
    return out, dup_report
