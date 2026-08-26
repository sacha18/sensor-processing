"""Step 4: sensor-specific signal correction.

Correction parameters aren't derived by this app - they're supplied by the
team, per sensor or sensor/group, as either a single multiplicative factor
(older sensors) or a two-factor linear correction (newer sensors). A sensor
with no matching row in the correction params table is left uncorrected
(signal_corrected stays NaN, flagged) rather than silently passed through -
an unconverted raw Signal count downstream would look like a very wrong VWC.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .params import first_match

_EXTRA_COLS = ["sensor_id", "correction_type", "factor_a", "factor_b"]


def apply_correction(qc: pd.DataFrame, correction_params: pd.DataFrame) -> pd.DataFrame:
    out = qc.copy()
    matched = first_match(out, correction_params, _EXTRA_COLS)

    signal = out["signal_qc"].astype(float)
    # .astype("float64"): an all-NULL factor_a/factor_b column (e.g. every
    # matched row is one_factor, so factor_b is never set) comes back from
    # DuckDB as a nullable Int type, not DOUBLE - force float64 so the
    # arithmetic below can't silently degrade to dtype=object.
    factor_a = pd.to_numeric(matched["factor_a"], errors="coerce").astype("float64")
    factor_b = pd.to_numeric(matched["factor_b"], errors="coerce").astype("float64")
    is_one = matched["correction_type"] == "one_factor"
    is_two = matched["correction_type"] == "two_factor"

    corrected = pd.Series(np.nan, index=out.index)
    corrected = corrected.where(~is_one, factor_a * signal)
    corrected = corrected.where(~is_two, factor_a * signal + factor_b)
    out["signal_corrected"] = corrected

    label = matched["sensor_id"].astype(str) + ":" + matched["correction_type"].astype(str)
    out["correction_id"] = np.where(is_one | is_two, label, np.nan)

    out["is_qc_missing_correction_params"] = out["signal_corrected"].isna() & out["signal_qc"].notna()
    return out
