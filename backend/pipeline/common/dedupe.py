"""Generic "keep one row per group, ranked by priority" dedup, usable on any
table regardless of its schema - a DuckDB window function replaces a sort +
drop_duplicates(keep=...), and generalizes to any partition/priority columns
instead of being hardcoded to one pipeline's notion of "latest write".

Used by the TMS pipeline (latest-downloaded file wins) to pick one row per
(sensor, timestamp) pair - kept here, not in pipeline/tms/, so a future
second pipeline with its own "latest wins" rule can reuse it instead of
reimplementing the same window-function query. Each pipeline keeps its own
duplicate-conflict report, since what counts as "conflicting" depends on its
own value columns.
"""
from __future__ import annotations

import pandas as pd

from .. import store


def dedupe_by_priority(df: pd.DataFrame, partition_cols: list[str], order_by_sql: str) -> pd.DataFrame:
    """Keeps exactly one row per `partition_cols` group: the one ranked first
    by `order_by_sql` (a raw SQL ORDER BY expression over columns already
    present in `df` - multi-column priority, ASC/DESC, is entirely the
    caller's choice). Output is sorted by `partition_cols`."""
    partition_sql = ", ".join(partition_cols)
    query = f"""
    SELECT * EXCLUDE (rn) FROM (
        SELECT *, row_number() OVER (
            PARTITION BY {partition_sql} ORDER BY {order_by_sql}
        ) AS rn
        FROM df
    ) WHERE rn = 1
    ORDER BY {partition_sql}
    """
    return store.sql_df(query, {"df": df})
