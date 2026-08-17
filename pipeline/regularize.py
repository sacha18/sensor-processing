"""Regularize onto a fixed time grid.

One common grid across all sensors; a sensor's own [first, last] observation
window marks which grid points are legitimately "in range" for it (points
outside that window are absence-of-deployment, not gaps to fill).
"""
from __future__ import annotations

import pandas as pd

from .config import STEP_MIN


def regularize(raw_long: pd.DataFrame, step_min: int = STEP_MIN):
    span = raw_long.groupby("sensor_id")["timestamp"].agg(obs_start="min", obs_end="max")
    grid = pd.date_range(span["obs_start"].min(), span["obs_end"].max(), freq=f"{step_min}min")

    rows = []
    for sensor_id, row in span.iterrows():
        sub = grid[(grid >= row["obs_start"]) & (grid <= row["obs_end"])]
        rows.append(pd.DataFrame({"sensor_id": sensor_id, "timestamp": sub}))
    reg = pd.concat(rows, ignore_index=True)
    reg = reg.merge(raw_long[["sensor_id", "timestamp", "value_raw"]], on=["sensor_id", "timestamp"], how="left")
    reg = reg.sort_values(["sensor_id", "timestamp"]).reset_index(drop=True)
    return reg, span, grid
