"""Shared row-matching helper for the correction (step 4) and calibration
(step 5) parameter tables: a params-table row applies to a reading if its
key matches either the sensor's own id or its metadata group_key, and (if
set) the reading's timestamp falls in [valid_from, valid_to]. A wildcard key
("*", "all", or blank) applies to every sensor - e.g. TOMST's own published
calibration is one universal equation, not one per sensor, so a single
sensor_id="*" row covers that case without requiring every sensor to share
a group_key.
"""
from __future__ import annotations

import logging
import time

import numpy as np
import pandas as pd

from .. import store

logger = logging.getLogger(__name__)

WILDCARD_KEYS = {"*", "all", ""}


def identity_mask(df: pd.DataFrame, key) -> pd.Series:
    """Whether `key` (a rule's sensor_id, possibly a wildcard) identifies any
    row of `df` - by sensor_id or, if present, group_key. Unlike
    `first_match`, no [valid_from, valid_to] filtering and no "first match
    wins" - used for small one-off checks (e.g. "does this rule still apply
    to any currently loaded sensor?"), not the per-reading correction/
    calibration join, so a plain pandas comparison is simpler and plenty
    fast at that scale."""
    key = str(key).strip()
    if key.lower() in WILDCARD_KEYS or pd.isna(key):
        return pd.Series(True, index=df.index)
    mask = df["sensor_id"].astype(str) == key
    if "group_key" in df.columns:
        mask |= df["group_key"].astype(str) == key
    return mask


_WILDCARD_SQL = "(sensor_id IS NULL OR lower(trim(CAST(sensor_id AS VARCHAR))) IN ('*', 'all', ''))"


def first_match(readings: pd.DataFrame, params_df: pd.DataFrame, extra_cols: list[str]) -> pd.DataFrame:
    """For each row of `readings`, finds the first row of `params_df` (in its
    original order - first configured rule wins, same as the old loop's
    `... & out[col].isna()` short-circuit) whose sensor_id/group_key and
    [valid_from, valid_to] window match. Replaces the old per-params-row
    `.iterrows()` + full-table boolean-mask loop (O(len(params_df) x
    len(readings)) in Python) with a DuckDB join + window function.

    The match condition (wildcard OR sensor_id-equals OR group_key-equals)
    is split into separate equi-joins (sensor_id, group_key) unioned with a
    cross-join against only the (normally few) wildcard rows - a single join
    with that OR baked into the ON clause can't be planned as a hash join,
    so DuckDB falls back to a nested-loop scan that's O(len(readings) x
    len(params_df)); on a real multi-million-row upload with even a modest
    params table, that's the difference between a sub-second join and one
    that takes tens of seconds.

    Returns a DataFrame aligned 1:1 with `readings` (same length/order) with
    `extra_cols` from the matched row (NaN/None where nothing matched) plus
    a boolean `_matched` column.
    """
    if params_df is None or params_df.empty:
        out = pd.DataFrame({c: pd.Series([None] * len(readings), dtype="object") for c in extra_cols}, index=readings.index)
        out["_matched"] = False
        return out

    has_group_key = "group_key" in readings.columns
    r_cols = ["sensor_id", "timestamp"] + (["group_key"] if has_group_key else [])
    r = readings[r_cols].reset_index(drop=True).copy()
    r["__row_id"] = np.arange(len(r))
    p = params_df.reset_index(drop=True).copy()
    p["__param_order"] = np.arange(len(p))

    def select(alias: str) -> str:
        return ", ".join(f'{alias}."{c}" AS "{c}"' for c in extra_cols)

    valid_window = "(p.valid_from IS NULL OR r.timestamp >= p.valid_from) AND (p.valid_to IS NULL OR r.timestamp <= p.valid_to)"

    branches = [f"""
        SELECT r.__row_id AS __row_id, {select('p')}, p.__param_order AS __param_order
        FROM r JOIN p ON CAST(r.sensor_id AS VARCHAR) = CAST(p.sensor_id AS VARCHAR)
        WHERE NOT {_WILDCARD_SQL.replace("sensor_id", "p.sensor_id")} AND {valid_window}
    """]
    if has_group_key:
        branches.append(f"""
        SELECT r.__row_id AS __row_id, {select('p')}, p.__param_order AS __param_order
        FROM r JOIN p ON r.group_key IS NOT NULL AND CAST(r.group_key AS VARCHAR) = CAST(p.sensor_id AS VARCHAR)
        WHERE NOT {_WILDCARD_SQL.replace("sensor_id", "p.sensor_id")} AND {valid_window}
        """)
    branches.append(f"""
        SELECT r.__row_id AS __row_id, {select('p')}, p.__param_order AS __param_order
        FROM r JOIN p ON {_WILDCARD_SQL.replace("sensor_id", "p.sensor_id")}
        WHERE {valid_window}
    """)

    query = f"""
    WITH matches AS ({" UNION ALL ".join(branches)}),
    ranked AS (
        SELECT *, row_number() OVER (PARTITION BY __row_id ORDER BY __param_order) AS rn FROM matches
    )
    SELECT r.__row_id AS __row_id, {select('ranked')}, (ranked.rn IS NOT NULL) AS _matched
    FROM r LEFT JOIN ranked ON r.__row_id = ranked.__row_id AND ranked.rn = 1
    ORDER BY r.__row_id
    """
    t0 = time.time()
    matched = store.sql_df(query, {"r": r, "p": p})
    sql_s = time.time() - t0
    t0 = time.time()
    matched = matched.sort_values("__row_id").drop(columns="__row_id").reset_index(drop=True)
    matched.index = readings.index
    post_s = time.time() - t0
    logger.info("first_match: %d reading(s) x %d param row(s) - sql=%.1fs, post=%.1fs",
                len(readings), len(params_df), sql_s, post_s)
    return matched
