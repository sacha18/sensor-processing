"""Small formatting/classification helpers, no chart dependency - shared
across both pipeline modes (hence the light pipeline.tms.config import for
file-format sniffing)."""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from pipeline.tms.config import FILENAME_RE as TMS_FILENAME_RE
from pipeline.tms.config import TIMESTAMP_FORMATS as TMS_TIMESTAMP_FORMATS

# above this many rows, a report table (e.g. a duplicate-pairs report on a
# large multi-hundred-file upload) is truncated on screen - Arrow-serializing
# and rendering millions of rows can stall or crash the browser tab. The full
# table is always still offered as a CSV download.
MAX_INLINE_ROWS = 5_000

# device telemetry (battery, radio signal, enclosure temp/humidity, firmware
# version, ...) rides along in the same export as real measurement channels but
# isn't a physical quantity to clean/compare - excluded from the pipeline by
# default (still selectable manually) so it doesn't dilute similarity/outlier
# results or get treated as if it were a comparable sensor
TELEMETRY_KEYWORDS = ["battery", "signal", "internal", "repeatcounter", "verfw", "credit"]


def is_telemetry_channel(sensor_id: str) -> bool:
    low = sensor_id.lower()
    return any(kw in low for kw in TELEMETRY_KEYWORDS)


def to_csv_bytes(df: pd.DataFrame, index: bool = True) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=index)
    return buf.getvalue().encode("utf-8")


@st.cache_data(show_spinner=False)
def to_csv_bytes_cached(df: pd.DataFrame, index: bool = True) -> bytes:
    """Same as to_csv_bytes, but memoized on the dataframe's content - a
    download_button's data= is recomputed on *every* app rerun (any widget
    interaction anywhere, not just clicking that button), so on a large
    merged/raw archive an uncached to_csv_bytes call re-serializes millions
    of rows to text over and over, which is slow enough to read as a crash."""
    return to_csv_bytes(df, index=index)


def to_xlsx_bytes(df: pd.DataFrame, index: bool = False) -> bytes:
    buf = io.BytesIO()
    df.to_excel(buf, index=index, engine="openpyxl")
    return buf.getvalue()


@st.cache_data(show_spinner=False)
def to_xlsx_bytes_cached(df: pd.DataFrame, index: bool = False) -> bytes:
    """Same memoization rationale as to_csv_bytes_cached."""
    return to_xlsx_bytes(df, index=index)


def render_capped_dataframe(df: pd.DataFrame, *, max_rows: int = MAX_INLINE_ROWS, **dataframe_kwargs) -> None:
    """Renders at most `max_rows` of `df` (pass it pre-sorted so the head is
    the part that matters) - a duplicate/gap report can reach millions of
    rows on a large multi-hundred-file upload, and handing that whole table
    to st.dataframe stalls Arrow serialization and can crash the browser
    tab. Pair with a CSV download button for access to the full table."""
    if len(df) > max_rows:
        st.caption(f"Showing the first {max_rows:,} of {len(df):,} rows (sorted as above) - "
                    "download the full CSV for the rest.")
        st.dataframe(df.head(max_rows), **dataframe_kwargs)
    else:
        st.dataframe(df, **dataframe_kwargs)


def looks_like_tms_export(name: str, content: bytes) -> bool:
    """Sniffs whether an upload looks like a TOMST TMS-4 raw export (the
    filename convention, or - in case it was renamed - a semicolon-separated
    first line whose first two fields are an integer row index and a
    yyyy.mm.dd HH:MM timestamp) - used to steer a file dropped in the wrong
    pipeline mode toward the right one instead of a confusing parse error."""
    if TMS_FILENAME_RE.search(Path(name).name):
        return True
    if Path(name).suffix.lower() != ".csv":
        return False
    try:
        first_line = content.decode("utf-8", errors="ignore").splitlines()[0]
        parts = first_line.split(";")
        if len(parts) < 9:
            return False
        int(parts[0])
        for fmt in TMS_TIMESTAMP_FORMATS:
            try:
                datetime.strptime(parts[1], fmt)
                return True
            except ValueError:
                continue
        return False
    except Exception:
        return False


def looks_like_generic_export(name: str, content: bytes) -> bool:
    """Sniffs whether an upload looks like the generic pipeline's format
    (JSON, or a CSV with phenomenon_time/result columns)."""
    suffix = Path(name).suffix.lower()
    if suffix == ".json":
        return True
    if suffix != ".csv":
        return False
    try:
        header = content.decode("utf-8", errors="ignore").splitlines()[0]
        cols = {c.strip().strip('"').lower() for c in header.split(",")}
        return "phenomenon_time" in cols and "result" in cols
    except Exception:
        return False
