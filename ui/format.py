"""Small formatting/classification helpers with no chart or pipeline dependency."""
from __future__ import annotations

import io

import pandas as pd

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
