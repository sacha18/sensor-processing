"""Step 5: calibration to volumetric water content (VWC).

The calibration equation is supplied by the team - a polynomial in the
corrected Signal (coefficients coef_0..coef_5; TOMST's own published
calibrations are typically cubic, arbitrary degree up to 5 is supported
here) - and can differ per sensor or sensor/group, resolved from metadata
the same way correction parameters are (params.match_mask) rather than
being hardcoded to one global equation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import POLY_COEF_COLUMNS
from .params import match_mask


def apply_calibration(corrected: pd.DataFrame, calibration_params: pd.DataFrame,
                       signal_col: str = "signal_corrected") -> pd.DataFrame:
    out = corrected.copy()
    out["vwc"] = np.nan
    out["calibration_id"] = pd.Series(dtype="object")

    if calibration_params is not None and not calibration_params.empty:
        for _, row in calibration_params.iterrows():
            if pd.isna(row.get("coef_0")):
                continue  # coef_0 acts as the sentinel that this row is actually configured
            degree = max(i for i, c in enumerate(POLY_COEF_COLUMNS) if pd.notna(row.get(c)))
            coefs = [row.get(c) if pd.notna(row.get(c)) else 0.0 for c in POLY_COEF_COLUMNS[:degree + 1]]

            mask = match_mask(out, row) & out["vwc"].isna()
            if not mask.any():
                continue
            out.loc[mask, "vwc"] = np.polyval(list(reversed(coefs)), out.loc[mask, signal_col])
            out.loc[mask, "calibration_id"] = f"{row['sensor_id']}:poly{degree}"

    out["is_qc_missing_calibration_params"] = out["vwc"].isna() & out[signal_col].notna()
    return out
