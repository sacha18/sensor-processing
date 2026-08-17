"""Outlier detection: four independent, toggleable methods catching different
fault modes. Each contributes its own is_outlier_<method> column; is_outlier
is their OR, so a point's flags stay individually inspectable instead of
collapsing to one bit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import DEFAULT_OUTLIER_CFG, HAMPEL_HALF_WINDOW, HAMPEL_K


# a) Hampel filter: flags points far (k MADs) from the median of a symmetric
# local window. A slow multi-step ramp (real event) stays inside the window's
# spread and is not flagged; an isolated spike is.

def hampel_flags(x: pd.Series, half_window: int = HAMPEL_HALF_WINDOW, k: float = HAMPEL_K) -> pd.Series:
    vals = x.to_numpy(dtype=float)
    n = len(vals)
    flags = np.zeros(n, dtype=bool)
    for i in range(n):
        if np.isnan(vals[i]):
            continue
        lo, hi = max(0, i - half_window), min(n, i + half_window + 1)
        w = vals[lo:hi]
        w = w[~np.isnan(w)]
        if len(w) < 3:
            continue
        med = np.median(w)
        mad = np.median(np.abs(w - med)) * 1.4826
        if mad == 0:
            continue
        if abs(vals[i] - med) > k * mad:
            flags[i] = True
    return pd.Series(flags, index=x.index)


# b) Flatline / stuck-sensor detector: a run of `min_run`+ back-to-back
# *identical* readings. Hampel structurally can't catch this (MAD is 0 inside
# a flatline, so it's skipped by design) - a distinct fault mode needs a
# distinct method.

def flatline_flags(x: pd.Series, min_run: int = 6) -> pd.Series:
    vals = x.to_numpy(dtype=float)
    n = len(vals)
    flags = np.zeros(n, dtype=bool)
    i = 0
    while i < n:
        if np.isnan(vals[i]):
            i += 1
            continue
        j = i + 1
        while j < n and vals[j] == vals[i]:
            j += 1
        if j - i >= min_run:
            flags[i:j] = True
        i = j
    return pd.Series(flags, index=x.index)


# c) Percentile / extreme-value clipping: flags readings outside this sensor's
# own [lo_pct, hi_pct] percentile range - a blunt, context-free sanity bound
# (e.g. a sign flip or a decimal-point glitch that a local window won't catch
# because the bad value doesn't look "sudden" relative to its own tiny run).

def percentile_flags(x: pd.Series, lo_pct: float = 0.5, hi_pct: float = 99.5) -> pd.Series:
    vals = x.to_numpy(dtype=float)
    finite = vals[~np.isnan(vals)]
    if len(finite) < 10:
        return pd.Series(np.zeros(len(vals), dtype=bool), index=x.index)
    lo, hi = np.percentile(finite, [lo_pct, hi_pct])
    flags = np.where(np.isnan(vals), False, (vals < lo) | (vals > hi))
    return pd.Series(flags, index=x.index)


# d) Rate-of-change filter: flags a step whose |delta| exceeds k times this
# sensor's own typical (median) step size. Self-calibrating per sensor, but
# unlike Hampel it has no window context, so a genuine sharp ramp (several
# large steps in the same direction) gets flagged too - off by default, opt-in
# for datasets known not to have legitimate rapid swings.

def rate_flags(x: pd.Series, k: float = 8.0) -> pd.Series:
    vals = x.to_numpy(dtype=float)
    n = len(vals)
    flags = np.zeros(n, dtype=bool)
    diffs = np.abs(np.diff(vals))
    finite = diffs[~np.isnan(diffs)]
    if len(finite) < 5:
        return pd.Series(flags, index=x.index)
    scale = np.median(finite)
    if scale == 0:
        scale = np.mean(finite)  # many exact-repeat steps (low-res sensor): median collapses to 0
    if scale == 0:
        return pd.Series(flags, index=x.index)
    thresh = k * scale
    for i in range(1, n):
        if np.isnan(vals[i]) or np.isnan(vals[i - 1]):
            continue
        if abs(vals[i] - vals[i - 1]) > thresh:
            flags[i] = True
    return pd.Series(flags, index=x.index)


def detect_outliers(reg_long: pd.DataFrame, outlier_cfg: dict = None) -> pd.DataFrame:
    cfg = {**DEFAULT_OUTLIER_CFG, **(outlier_cfg or {})}
    out = reg_long.copy()
    g = out.groupby("sensor_id")["value_raw"]

    out["is_outlier_hampel"] = g.transform(lambda s: hampel_flags(s, cfg["hampel_half_window"], cfg["hampel_k"])) if cfg["use_hampel"] else False
    out["is_outlier_flatline"] = g.transform(lambda s: flatline_flags(s, cfg["flatline_min_run"])) if cfg["use_flatline"] else False
    out["is_outlier_range"] = g.transform(lambda s: percentile_flags(s, cfg["pct_low"], cfg["pct_high"])) if cfg["use_percentile"] else False
    out["is_outlier_rate"] = g.transform(lambda s: rate_flags(s, cfg["rate_k"])) if cfg["use_rate"] else False

    method_cols = ["is_outlier_hampel", "is_outlier_flatline", "is_outlier_range", "is_outlier_rate"]
    out["is_outlier"] = out[method_cols].any(axis=1)
    out["value_qc"] = out["value_raw"].where(~out["is_outlier"])
    return out
