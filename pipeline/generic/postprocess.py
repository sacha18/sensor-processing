"""Post-processing: aggregation & smoothing.

Both operate on the cleaned+gap-filled value_clean series, downstream of QC -
neither feeds back into it, so the raw-resolution production series stays intact.
"""
from __future__ import annotations

import pandas as pd

from .config import AGG_FREQ, SMOOTH_METHOD, SMOOTH_WINDOW


def aggregate(production: pd.DataFrame, freq: str = AGG_FREQ) -> pd.DataFrame:
    """Per-sensor summary stats (mean/min/max/std/count) over a coarser time bucket
    (e.g. daily), one row per (period, sensor)."""
    agg = (
        production.set_index("timestamp")
        .groupby(["sensor_id", pd.Grouper(freq=freq)])["value_clean"]
        .agg(["mean", "min", "max", "std", "count"])
        .reset_index()
        .rename(columns={"timestamp": "period"})
        .sort_values(["sensor_id", "period"])
        .reset_index(drop=True)
    )
    return agg


def smooth(production_wide: pd.DataFrame, window: int = SMOOTH_WINDOW, method: str = SMOOTH_METHOD) -> pd.DataFrame:
    """Rolling mean/median over the cleaned wide series - a trend/display aid
    layered on top of value_clean, not a replacement for it."""
    roll = production_wide.rolling(window=window, center=True, min_periods=1)
    return roll.median() if method == "median" else roll.mean()
