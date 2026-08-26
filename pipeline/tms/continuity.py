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

import logging

import pandas as pd

from .. import store
from .config import DEFAULT_STEP_MIN, GAP_TOLERANCE
from .io import download_sort_key

logger = logging.getLogger(__name__)

VALUE_COLS = ["t1_raw", "t2_raw", "t3_raw", "signal_raw"]

_DUP_REPORT_QUERY = f"""
SELECT sensor_id, timestamp, COUNT(*) AS n_dup,
       {", ".join(f'COUNT(DISTINCT {c}) AS n_distinct_{c}' for c in VALUE_COLS)},
       ({" OR ".join(f'COUNT(DISTINCT {c}) > 1' for c in VALUE_COLS)}) AS conflicting
FROM raw_wide
GROUP BY sensor_id, timestamp
HAVING COUNT(*) > 1
"""

_MERGE_QUERY = """
SELECT * EXCLUDE (rn) FROM (
    SELECT raw_wide.*, row_number() OVER (
        PARTITION BY raw_wide.sensor_id, raw_wide.timestamp
        ORDER BY k.dl_year DESC, k.dl_month DESC, k.dl_day DESC, k.dl_part DESC
    ) AS rn
    FROM raw_wide JOIN file_keys k ON raw_wide.source_file = k.source_file
) WHERE rn = 1
ORDER BY sensor_id, timestamp
"""


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
    """Overlapping timestamps are resolved by keeping the row from whichever
    file was downloaded last - a DuckDB window function (ranked by a small
    per-file sort-key table, not a Python `.map()` over every row) replaces
    the old sort + drop_duplicates(keep='last')."""
    sources = {"raw_wide": raw_wide}
    dup_report = store.sql_df(_DUP_REPORT_QUERY, sources)

    # download_sort_key parses (year, month, day, part) from a filename via
    # regex - computed once per distinct source_file (not once per row like
    # the old `.map()` over the whole column) and joined in.
    unique_files = raw_wide["source_file"].unique()
    file_keys = pd.DataFrame(
        [(f, *download_sort_key(f)) for f in unique_files],
        columns=["source_file", "dl_year", "dl_month", "dl_day", "dl_part"],
    )
    out = store.sql_df(_MERGE_QUERY, {"raw_wide": raw_wide, "file_keys": file_keys})

    logger.info("TMS merge_and_dedupe: %d row(s) in, %d row(s) out, %d duplicate (sensor, timestamp) pair(s) "
                "across %d sensor(s)", len(raw_wide), len(out), len(dup_report), raw_wide["sensor_id"].nunique())
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
