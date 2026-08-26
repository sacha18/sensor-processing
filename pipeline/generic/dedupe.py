"""De-duplicate repeated (sensor, timestamp) observations.

Keeps the highest observation_id (most recent write) for any repeated
sensor/timestamp pair. The report flags which duplicate groups are
"conflicting" - i.e. the repeated rows don't even agree on value_raw, so
silently keeping the last write is discarding a real disagreement, not just
a harmless re-transmission.
"""
from __future__ import annotations

import pandas as pd

from .. import store

_DEDUPE_QUERY = """
SELECT * EXCLUDE (rn) FROM (
    SELECT *, row_number() OVER (
        PARTITION BY sensor_id, timestamp ORDER BY CAST(observation_id AS BIGINT) DESC
    ) AS rn
    FROM raw_long
) WHERE rn = 1
ORDER BY sensor_id, timestamp
"""

_DUP_REPORT_QUERY = """
SELECT sensor_id, timestamp, COUNT(*) AS n_dup,
       COUNT(DISTINCT value_raw) AS n_distinct_values,
       MIN(value_raw) AS value_min, MAX(value_raw) AS value_max,
       MAX(value_raw) - MIN(value_raw) AS value_spread,
       COUNT(DISTINCT value_raw) > 1 AS conflicting
FROM raw_long
GROUP BY sensor_id, timestamp
HAVING COUNT(*) > 1
"""


def dedupe(raw_long: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keeps the highest observation_id (most recent write) for any repeated
    (sensor, timestamp) pair - a DuckDB window function replaces the old
    sort + drop_duplicates(keep='last')."""
    sources = {"raw_long": raw_long}
    out = store.sql_df(_DEDUPE_QUERY, sources)
    dup_report = store.sql_df(_DUP_REPORT_QUERY, sources)
    return out, dup_report
