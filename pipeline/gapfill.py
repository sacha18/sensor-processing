"""Gap filling.

a) outliers            -> imputed straight from the most correlated sensor
                           (a lone outlier is a 1-step "gap" that linear
                           interpolation would otherwise just paper over with
                           its neighbours, ignoring the correlated signal we
                           already have for that exact timestamp)
b) short in-range gaps  -> linear time-interpolation
c) longer in-range gaps -> linear regression on the most similar donor sensor
d) anything left        -> NaN, flagged unfilled
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import DONOR_MIN_CORR, MAX_INTERP_GAP, USE_DONOR_REGRESSION


def interp_short_gaps(x: pd.Series, max_gap: int = MAX_INTERP_GAP):
    vals = x.to_numpy(dtype=float).copy()
    n = len(vals)
    method = np.array([None] * n, dtype=object)
    is_na = np.isnan(vals)

    i = 0
    while i < n:
        if not is_na[i]:
            i += 1
            continue
        j = i
        while j < n and is_na[j]:
            j += 1
        gap_len = j - i
        if i == 0 or j == n:
            method[i:j] = "edge_unfilled"
        elif gap_len <= max_gap:
            x0, x1 = vals[i - 1], vals[j]
            vals[i:j] = np.interp(np.arange(1, gap_len + 1), [0, gap_len + 1], [x0, x1])
            method[i:j] = "linear_interp"
        i = j
    return pd.Series(vals, index=x.index), pd.Series(method, index=x.index)


def fit_donor_regression(target: pd.Series, donor: pd.Series):
    """Fit target ~ a*donor + b on timestamps where both are observed. None if
    there aren't enough paired points to fit a meaningful line."""
    ok = target.notna() & donor.notna()
    if ok.sum() < 5:
        return None
    return np.polyfit(donor[ok], target[ok], 1)


def donor_fill(target: pd.Series, donor: pd.Series, method: pd.Series, mask: pd.Series = None, label: str = "donor_regression"):
    """Impute `target` at positions where it's NaN, `method` is unset, and (if given)
    `mask` is True, from a regression fit against `donor`. Every filled position is
    tagged `label` in the returned method series."""
    target = target.copy()
    method = method.copy()
    need = target.isna() & method.isna()
    if mask is not None:
        need = need & mask
    if not need.any() or donor.isna().all():
        return target, method
    fit = fit_donor_regression(target, donor)
    if fit is not None:
        a, b = fit
        can_predict = need & donor.notna()
        target.loc[can_predict] = a * donor.loc[can_predict] + b
        method.loc[can_predict] = label
    return target, method


def gap_fill(reg_long: pd.DataFrame, sim: dict, max_gap: int = MAX_INTERP_GAP,
             use_donor_regression: bool = USE_DONOR_REGRESSION, donor_min_corr: float = DONOR_MIN_CORR):
    wide_qc = sim["wide_qc"]
    wide_outlier = reg_long.pivot(index="timestamp", columns="sensor_id", values="is_outlier").reindex(columns=wide_qc.columns).sort_index()

    # a donor is only trusted to impute if it clears the minimum correlation -
    # a weakly-correlated "most similar" sensor is still the best of a bad lot,
    # but regressing on it would just inject noise
    eligible_donor = {}
    for s in wide_qc.columns:
        donor = sim["donor_of"].get(s)
        corr = sim["cor_level"].loc[s, donor] if (donor is not None and use_donor_regression) else None
        eligible_donor[s] = donor if (corr is not None and pd.notna(corr) and abs(corr) >= donor_min_corr) else None

    # stage 0: outliers imputed straight from the correlated donor (skips the
    # gap-length heuristic entirely - we already have a same-timestamp reading
    # from a correlated sensor, no need to fall back to interpolating neighbours)
    stage0_vals, stage0_method = {}, {}
    for s in wide_qc.columns:
        v = wide_qc[s]
        m = pd.Series([None] * len(v), index=v.index, dtype=object)
        donor = eligible_donor[s]
        if donor is not None:
            v, m = donor_fill(v, wide_qc[donor], m, mask=wide_outlier[s].fillna(False), label="outlier_donor_regression")
        stage0_vals[s], stage0_method[s] = v, m
    stage0 = pd.DataFrame(stage0_vals)
    method0 = pd.DataFrame(stage0_method)

    # stage 1: remaining short in-range gaps -> linear interpolation
    stage1_vals, stage1_method = {}, {}
    for s in stage0.columns:
        v, m = interp_short_gaps(stage0[s], max_gap)
        stage1_vals[s], stage1_method[s] = v, m.where(method0[s].isna(), method0[s])
    stage1 = pd.DataFrame(stage1_vals)
    method1 = pd.DataFrame(stage1_method)

    # stage 2: remaining longer gaps -> donor regression
    stage2 = stage1.copy()
    method2 = method1.copy()
    for s in stage1.columns:
        donor = eligible_donor[s]
        if donor is None:
            still_na = stage2[s].isna() & method2[s].isna()
            method2.loc[still_na, s] = "unfilled"
            continue
        v, m = donor_fill(stage1[s], stage1[donor], method1[s], label="donor_regression")
        m.loc[v.isna() & m.isna()] = "unfilled"
        stage2[s] = v
        method2[s] = m

    value_clean_long = stage2.reset_index().melt(id_vars="timestamp", var_name="sensor_id", value_name="value_clean")
    method_long = method2.reset_index().melt(id_vars="timestamp", var_name="sensor_id", value_name="fill_method")

    production = reg_long.merge(value_clean_long, on=["sensor_id", "timestamp"], how="left")
    production = production.merge(method_long, on=["sensor_id", "timestamp"], how="left")
    observed_mask = production["fill_method"].isna() & production["value_raw"].notna() & ~production["is_outlier"]
    production.loc[observed_mask, "fill_method"] = "observed"
    production["fill_method"] = production["fill_method"].fillna("unfilled")
    return production.sort_values(["sensor_id", "timestamp"]).reset_index(drop=True), stage1, method1
