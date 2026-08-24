"""Step 1: loading / merge / continuity.

Multiple downloads of the same physical sensor (grouped by the serial
extracted from the filename) get merged onto one timeline: overlapping
timestamps are resolved by keeping the row from whichever file was
downloaded last (a re-download is a superset re-read of the logger's
memory, so the latest download is the most complete/authoritative one for
any timestamp both files cover), exact duplicate rows collapse, and any
remaining hole in the timeline is reported - never filled here.
"""
from __future__ import annotations

import pandas as pd

from .config import DEFAULT_STEP_MIN, GAP_TOLERANCE
from .io import download_sort_key

VALUE_COLS = ["t1_raw", "t2_raw", "t3_raw", "signal_raw"]


def infer_step_minutes(ts: pd.Series) -> int:
    diffs = ts.sort_values().diff().dropna()
    if diffs.empty:
        return DEFAULT_STEP_MIN
    mode = diffs.mode()
    if mode.empty:
        return DEFAULT_STEP_MIN
    minutes = int(round(mode.iloc[0].total_seconds() / 60))
    return minutes if minutes > 0 else DEFAULT_STEP_MIN


def merge_and_dedupe(raw_wide: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    dup_counts = raw_wide.groupby(["sensor_id", "timestamp"]).size()
    dup_keys = dup_counts[dup_counts > 1].reset_index(name="n_dup")

    nunique = raw_wide.groupby(["sensor_id", "timestamp"])[VALUE_COLS].nunique().reset_index()
    dup_report = dup_keys.merge(nunique, on=["sensor_id", "timestamp"])
    dup_report["conflicting"] = (dup_report[VALUE_COLS] > 1).any(axis=1)
    dup_report = dup_report.rename(columns={c: f"n_distinct_{c}" for c in VALUE_COLS})

    out = raw_wide.copy()
    out["_sort_key"] = out["source_file"].map(download_sort_key)
    out = (
        out.sort_values("_sort_key")
        .drop_duplicates(subset=["sensor_id", "timestamp"], keep="last")
        .drop(columns="_sort_key")
        .sort_values(["sensor_id", "timestamp"])
        .reset_index(drop=True)
    )
    return out, dup_report


def detect_gaps(merged: pd.DataFrame, step_min: int | None = None) -> pd.DataFrame:
    """Per sensor: any inter-sample delta more than GAP_TOLERANCE x the
    (inferred or given) nominal step becomes one reported gap. No filling."""
    rows = []
    for sensor_id, g in merged.groupby("sensor_id"):
        ts = g["timestamp"].sort_values().reset_index(drop=True)
        step = step_min if step_min is not None else infer_step_minutes(ts)
        nominal = pd.Timedelta(minutes=step)
        deltas = ts.diff()
        for i in deltas[deltas > nominal * GAP_TOLERANCE].index:
            gap_start, gap_end = ts.iloc[i - 1], ts.iloc[i]
            rows.append({
                "sensor_id": sensor_id,
                "gap_start": gap_start,
                "gap_end": gap_end,
                "expected_step_min": step,
                "n_missing_steps": int(round((gap_end - gap_start) / nominal)) - 1,
                "gap_duration": gap_end - gap_start,
            })
    columns = ["sensor_id", "gap_start", "gap_end", "expected_step_min", "n_missing_steps", "gap_duration"]
    return pd.DataFrame(rows, columns=columns)
