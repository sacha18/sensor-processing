"""Small formatting/classification helpers, no chart dependency - shared
across both pipeline modes (hence the light pipeline.tms.config import for
file-format sniffing)."""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import pandas as pd

from pipeline.tms.config import FILENAME_RE as TMS_FILENAME_RE
from pipeline.tms.config import TIMESTAMP_FORMAT as TMS_TIMESTAMP_FORMAT

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
        datetime.strptime(parts[1], TMS_TIMESTAMP_FORMAT)
        return True
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
