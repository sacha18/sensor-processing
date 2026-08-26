"""Outlier detection: four independent, toggleable methods catching different
fault modes. Each contributes its own is_outlier_<method> column; is_outlier
is their OR, so a point's flags stay individually inspectable instead of
collapsing to one bit.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from .config import DEFAULT_OUTLIER_CFG, HAMPEL_HALF_WINDOW, HAMPEL_K


# a) Hampel filter: flags points far (k MADs) from the median of a symmetric
# local window. A slow multi-step ramp (real event) stays inside the window's
# spread and is not flagged; an isolated spike is.
#
# Vectorized via a sliding window over the whole series at once (numpy
# stride_tricks) rather than a per-point Python loop - the loop was the
# pipeline's dominant cost by a wide margin (~40x the rest combined on a
# multi-sensor TMS run), since it reran on every parameter tweak for every
# sensor/channel. NaN-padding both ends before windowing reproduces the
# original's truncated (not centered-with-fabricated-data) edge windows:
# nanmedian over the padding NaNs plus the real edge values is exactly the
# median of just those real values, same as the old lo/hi-clamped slice.

def hampel_flags(x: pd.Series, half_window: int = HAMPEL_HALF_WINDOW, k: float = HAMPEL_K) -> pd.Series:
    vals = x.to_numpy(dtype=float)
    n = len(vals)
    if n == 0:
        return pd.Series(vals, index=x.index, dtype=bool)

    padded = np.concatenate([np.full(half_window, np.nan), vals, np.full(half_window, np.nan)])
    windows = np.lib.stride_tricks.sliding_window_view(padded, 2 * half_window + 1)  # (n, window)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)  # all-NaN window -> nan, filtered out below
        med = np.nanmedian(windows, axis=1)
        counts = np.sum(~np.isnan(windows), axis=1)
        mad = np.nanmedian(np.abs(windows - med[:, None]), axis=1) * 1.4826

    flags = ~np.isnan(vals) & (counts >= 3) & (mad > 0) & (np.abs(vals - med) > k * mad)
    return pd.Series(flags, index=x.index)


# b) Flatline / stuck-sensor detector: a run of `min_run`+ back-to-back
# *identical* readings. Hampel structurally can't catch this (MAD is 0 inside
# a flatline, so it's skipped by design) - a distinct fault mode needs a
# distinct method.
#
# Vectorized via run-length encoding (cumsum of "value changed from the
# previous one" as a run id, bincount to get each run's length) rather than
# a per-point Python while-loop - on a real multi-sensor, multi-channel TMS
# run (52 sensors x 4 channels x ~120k points) the loop was the dominant
# cost of the whole initial-QC stage.

def flatline_flags(x: pd.Series, min_run: int = 6) -> pd.Series:
    vals = x.to_numpy(dtype=float)
    n = len(vals)
    if n == 0:
        return pd.Series(vals, index=x.index, dtype=bool)

    valid = ~np.isnan(vals)
    # a new run starts wherever the value differs from the previous one, or
    # either side of the pair is NaN (a NaN never joins/extends a run)
    starts_new_run = np.ones(n, dtype=bool)
    starts_new_run[1:] = ~((vals[1:] == vals[:-1]) & valid[1:] & valid[:-1])
    run_id = np.cumsum(starts_new_run) - 1

    run_lengths = np.zeros(n, dtype=np.int64)
    if valid.any():
        counts = np.bincount(run_id[valid])
        run_lengths[valid] = counts[run_id[valid]]

    flags = valid & (run_lengths >= min_run)
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
#
# Vectorized: `diffs > thresh` is False wherever `diffs` is NaN (any IEEE-754
# comparison against NaN is False), which is exactly the old loop's explicit
# `if isnan(...): continue` skip - no per-point Python loop needed.

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
    flags[1:] = diffs > thresh
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
