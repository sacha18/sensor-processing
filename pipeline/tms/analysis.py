"""Step 7: downstream analysis of the finished production dataset - physical
depth reassignment for T1/T2/T3, and the group-mean/daily-aggregate helpers
every analysis chart is built from. Nothing here feeds back into the
pipeline (see pipeline/tms/production.py); it's read-only reporting on top
of the already-cleaned `production` table.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import NEAR_SURFACE_POSITION

# T1/T2/T3 are only physically meaningful at their real height once the
# probe's install depth is known. depth_cm already uses this app's own
# "negative = below surface" convention (see ui/tms/steps/metadata.py's
# column help) - a near-surface install has all three channels in play at
# their fixed protocol offsets (soil/surface/air); any deeper install only
# has T1 buried at the install depth (T2/T3 would be measuring the
# borehole, not soil - not meaningful, dropped).
NEAR_SURFACE_DEPTH_CM = 14
NEAR_SURFACE_Z_CM = {"t1": -8, "t2": 0, "t3": 15}
_QC_FLAG_COL = {"t1": "is_qc_t1", "t2": "is_qc_t2", "t3": "is_qc_t3"}
_META_COLS = ["timestamp", "sensor_id", "site", "treatment"]


def assign_temperature_levels(production: pd.DataFrame) -> pd.DataFrame:
    """Long-form (one row per reading x channel) temperature table with each
    channel's real physical position `z_cm` - T1/T2/T3 at their near-surface
    offsets for a near-surface install, or just T1 at depth_cm (T2/T3
    dropped as not meaningful) for any deeper install. Readings flagged by
    initial QC on that channel (is_qc_t1/t2/t3) are excluded, same
    "invalid -> not plotted, not silently averaged in" treatment as
    vwc_final downstream.

    Near-surface is decided by `position` (== NEAR_SURFACE_POSITION), not
    depth_cm: the metadata step's own auto-seed (ui/tms/steps/metadata.py)
    prefills position="near_surface" for every freshly loaded sensor but
    leaves depth_cm blank - keying off depth_cm alone would drop T1/T2/T3
    for the common case of a user who never touched that field. depth_cm's
    magnitude is still checked as a fallback, for metadata uploads that set
    it directly without ever setting position."""
    # to_numeric, not a bare .abs(): depth_cm is user-entered metadata (see
    # ui/tms/config.py's schema coercion) - a row missing it entirely can
    # still reach here as an object-dtype None rather than a proper float
    # NaN, and abs(None) raises.
    depth_cm = pd.to_numeric(production["depth_cm"], errors="coerce")
    near_surface = (production["position"] == NEAR_SURFACE_POSITION) | (depth_cm.abs() == NEAR_SURFACE_DEPTH_CM)
    meta_cols = [c for c in _META_COLS if c in production.columns]
    parts = []
    for ch in ("t1", "t2", "t3"):
        col = f"{ch}_raw"
        if col not in production.columns:
            continue
        z = pd.Series(np.nan, index=production.index, dtype=float)
        z[near_surface] = NEAR_SURFACE_Z_CM[ch]
        if ch == "t1":
            z[~near_surface] = -depth_cm[~near_surface].abs()

        temp = production[col]
        flag_col = _QC_FLAG_COL[ch]
        if flag_col in production.columns:
            temp = temp.where(~production[flag_col].fillna(False))

        keep = z.notna() & temp.notna()
        if not keep.any():
            continue
        part = production.loc[keep, meta_cols].copy()
        part["channel"] = ch
        part["z_cm"] = z[keep]
        part["temperature"] = temp[keep]
        parts.append(part)
    return pd.concat(parts, ignore_index=True) if parts else production.iloc[0:0][meta_cols].assign(
        channel=pd.Series(dtype="object"), z_cm=pd.Series(dtype="float64"), temperature=pd.Series(dtype="float64"))


def group_mean(df: pd.DataFrame, value_col: str, group_cols: list[str], time_col: str = "timestamp") -> pd.DataFrame:
    """Cross-sensor mean of value_col at each shared timestamp, within each
    group_cols combination (e.g. treatment x depth) - the thick "group
    average" line layered over the thin per-sensor lines. Carries n
    (contributing sensor count at that timestamp) so a point averaged over
    only one or two sensors isn't shown with the same visual weight as one
    averaged over a full group."""
    # dropna=False: a sensor missing treatment/depth metadata must not silently
    # vanish from the average - it still gets its own "(unset)" group instead.
    g = df.groupby(group_cols + [time_col], dropna=False)[value_col]
    out = g.agg(mean="mean", n="count").reset_index()
    return out


def resample_stats(df: pd.DataFrame, value_col: str, group_cols: list[str], freq: str) -> pd.DataFrame:
    """One row per (group..., period) at the given pandas offset alias
    (e.g. "h", "D", "W", "MS") - mean/max/min/std of value_col, plus n =
    count of valid observations in that period. General-purpose version of
    daily_stats for the free-form exploration section (ui/tms/steps/analysis.py)."""
    grouper = pd.Grouper(key="timestamp", freq=freq)
    return (df.groupby(group_cols + [grouper], dropna=False)[value_col]
            .agg(mean="mean", max="max", min="min", std="std", n="count")
            .reset_index())


def daily_stats(df: pd.DataFrame, value_col: str, group_cols: list[str]) -> pd.DataFrame:
    """One row per (group..., calendar day): mean/max/min of value_col, plus
    n = count of valid (non-NA) observations that day. TMS-4's nominal
    15-min step means a full day is n=96; a day with n well below that is
    less reliable and should be flagged in a tooltip, not trusted the same
    as a full day."""
    dated = df.assign(date=pd.to_datetime(df["timestamp"]).dt.floor("D"))
    return (dated.groupby(group_cols + ["date"], dropna=False)[value_col]
            .agg(mean="mean", max="max", min="min", n="count")
            .reset_index())


def daily_group_mean(daily_per_sensor: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """Second-stage aggregate over an already-per-sensor daily_stats() table
    - the mean of each sensor's own daily mean within the group (aggregate
    per sensor first, then across sensors - not a single pooled mean over
    every raw reading, which would silently over-weight whichever sensor
    happened to have more valid readings that day). n = number of
    contributing sensors that day."""
    return (daily_per_sensor.groupby(group_cols + ["date"], dropna=False)["mean"]
            .agg(mean="mean", n="count")
            .reset_index())
