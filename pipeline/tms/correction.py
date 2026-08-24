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

from .params import match_mask

CORRECTION_FORMULAS = {
    "one_factor": lambda signal, row: row["factor_a"] * signal,
    "two_factor": lambda signal, row: row["factor_a"] * signal + row["factor_b"],
}


def apply_correction(qc: pd.DataFrame, correction_params: pd.DataFrame) -> pd.DataFrame:
    out = qc.copy()
    out["signal_corrected"] = np.nan
    out["correction_id"] = pd.Series(dtype="object")

    if correction_params is not None and not correction_params.empty:
        for _, row in correction_params.iterrows():
            formula = CORRECTION_FORMULAS.get(row.get("correction_type"))
            if formula is None:
                continue
            mask = match_mask(out, row) & out["signal_corrected"].isna()
            if not mask.any():
                continue
            out.loc[mask, "signal_corrected"] = formula(out.loc[mask, "signal_qc"], row)
            out.loc[mask, "correction_id"] = f"{row['sensor_id']}:{row['correction_type']}"

    out["is_qc_missing_correction_params"] = out["signal_corrected"].isna() & out["signal_qc"].notna()
    return out
