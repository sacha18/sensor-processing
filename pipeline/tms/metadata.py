"""Step 2: metadata assignment.

Deployment metadata (site, treatment, position, depth, install period, ...)
lives in its own table - one row per sensor per install period, since a
logger can be redeployed - rather than being hardcoded (see ui/tms/config.py
for how that table gets populated, by upload and/or manual edit). A reading
is matched to whichever metadata row's [install_start, install_end] window
contains its timestamp; readings matching no window are excluded from the
working series and reported separately, per spec.
"""
from __future__ import annotations

import pandas as pd

from .. import store

METADATA_COLUMNS = [
    "sensor_id", "group_key", "site", "treatment", "position", "position_depth",
    "row", "transect", "depth_cm", "t1_label", "t2_label", "t3_label",
    "install_start", "install_end", "notes",
]
_EXTRA_COLUMNS = [c for c in METADATA_COLUMNS if c != "sensor_id"]

# A reading can match more than one install period if they overlap for the
# same sensor - a plain (not deduplicating) INNER JOIN reproduces that
# one-input-row -> N-output-rows fan-out exactly like the original
# iterrows()-per-metadata-row loop did.
_JOIN_QUERY = f"""
WITH meta AS (
    SELECT *, row_number() OVER () - 1 AS install_id FROM metadata_df
)
SELECT merged.*, {", ".join(f'meta."{c}"' for c in _EXTRA_COLUMNS)}, meta.install_id
FROM merged
JOIN meta
    ON CAST(merged.sensor_id AS VARCHAR) = CAST(meta.sensor_id AS VARCHAR)
    AND (meta.install_start IS NULL OR merged.timestamp >= meta.install_start)
    AND (meta.install_end IS NULL OR merged.timestamp <= meta.install_end)
ORDER BY merged.sensor_id, merged.timestamp
"""

_ANTI_JOIN_QUERY = """
WITH meta AS (SELECT * FROM metadata_df)
SELECT merged.* FROM merged
WHERE NOT EXISTS (
    SELECT 1 FROM meta
    WHERE CAST(merged.sensor_id AS VARCHAR) = CAST(meta.sensor_id AS VARCHAR)
    AND (meta.install_start IS NULL OR merged.timestamp >= meta.install_start)
    AND (meta.install_end IS NULL OR merged.timestamp <= meta.install_end)
)
ORDER BY merged.sensor_id, merged.timestamp
"""


def _empty_metadata_df() -> pd.DataFrame:
    # explicit dtypes (not just an empty object-dtype frame) so DuckDB's
    # bind-time type check on `merged.timestamp >= meta.install_start` etc.
    # doesn't choke on a TIMESTAMP-vs-VARCHAR mismatch when there's no data.
    dtypes = {c: "datetime64[ns]" if c in ("install_start", "install_end") else "object" for c in METADATA_COLUMNS}
    return pd.DataFrame({c: pd.Series(dtype=dt) for c, dt in dtypes.items()})


def apply_metadata(merged: pd.DataFrame, metadata_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    has_metadata = metadata_df is not None and not metadata_df.empty
    metadata_df = metadata_df if has_metadata else _empty_metadata_df()
    sources = {"merged": merged, "metadata_df": metadata_df}

    with_metadata = store.sql_df(_JOIN_QUERY, sources)
    excluded = store.sql_df(_ANTI_JOIN_QUERY, sources)
    excluded["reason"] = "outside_install_period" if has_metadata else "no_metadata_configured"

    return with_metadata, excluded
