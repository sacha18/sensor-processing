"""Step 5: calibration to volumetric water content (VWC).

The calibration equation is supplied by the team - a polynomial in the
corrected Signal (coefficients coef_0..coef_5; TOMST's own published
calibrations are typically cubic, arbitrary degree up to 5 is supported
here) - and can differ per sensor or sensor/group, resolved from metadata
the same way correction parameters are (params.first_match) rather than
being hardcoded to one global equation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import POLY_COEF_COLUMNS
from .params import first_match

_EXTRA_COLS = ["sensor_id", *POLY_COEF_COLUMNS]


def apply_calibration(corrected: pd.DataFrame, calibration_params: pd.DataFrame,
                       signal_col: str = "signal_corrected") -> pd.DataFrame:
    out = corrected.copy()
    matched = first_match(out, calibration_params, _EXTRA_COLS)

    # coef_0 is the sentinel that a matched row is actually configured (same
    # rule as the original per-row loop) - a matched-but-unconfigured row
    # (all coefs NaN) is treated the same as "nothing matched".
    configured = matched["coef_0"].notna() if len(matched) else pd.Series([], dtype=bool)

    # DuckDB infers an all-NULL column (e.g. an unused higher-degree coef_N
    # across every matched row) as a nullable Int type, not DOUBLE - forcing
    # float64 here keeps the later `.to_numpy()` a homogeneous float array
    # instead of silently falling back to dtype=object.
    coefs = matched[POLY_COEF_COLUMNS].apply(lambda s: pd.to_numeric(s, errors="coerce").astype("float64"))
    # degree = highest coef index that's non-null - only meaningful (and only
    # used) for the `calibration_id` label; the polyval below is invariant to
    # NaN-as-0 substitution up to any unused higher-degree terms, so it's
    # computed separately rather than gating the coefficient values below.
    notna = coefs.notna().to_numpy()
    has_any = notna.any(axis=1)
    degree = np.where(has_any, notna.shape[1] - 1 - notna[:, ::-1].argmax(axis=1), 0)

    # np.polyval(p, x) = p[0]*x**(N-1) + ... + p[-1]; coefs are stored
    # low-to-high degree (coef_0 = constant term), so reverse them, treating
    # any NaN (unset) coefficient as 0 - mathematically identical to the
    # original's degree-truncated coefficient list.
    coef_matrix = coefs[POLY_COEF_COLUMNS[::-1]].fillna(0.0).to_numpy()
    signal = out[signal_col].astype(float).to_numpy()
    # Horner's method, vectorized across rows (each row can have different
    # coefficients, unlike np.polyval which assumes one shared coefficient
    # set) - a fixed handful of passes over the whole column, not a Python
    # loop per reading.
    vwc = np.zeros(len(out))
    for j in range(coef_matrix.shape[1]):
        vwc = vwc * signal + coef_matrix[:, j]
    out["vwc"] = np.where(configured, vwc, np.nan) if len(out) else vwc

    label = matched["sensor_id"].astype(str) + ":poly" + pd.Series(degree, index=out.index).astype(str)
    out["calibration_id"] = np.where(configured, label, np.nan) if len(out) else pd.Series(dtype="object")

    out["is_qc_missing_calibration_params"] = out["vwc"].isna() & out[signal_col].notna()
    return out
