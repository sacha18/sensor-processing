"""Step 7: production dataset - one row per sensor/timestamp with everything
downstream steps produced, in a fixed column order."""
from __future__ import annotations

import pandas as pd

PRODUCTION_COLUMNS = [
    "timestamp", "sensor_id", "site", "treatment", "position", "position_depth",
    "row", "transect", "depth_cm", "install_id",
    "t1_label", "t2_label", "t3_label",
    "t1_raw", "t2_raw", "t3_raw", "signal_raw",
    "signal_corrected", "signal_corrected_final", "vwc", "vwc_final",
    "source_file", "correction_id", "calibration_id",
    "is_qc_t1", "is_qc_t2", "is_qc_t3", "is_qc_signal", "is_qc_device_error",
    "is_qc_missing_correction_params", "is_qc_missing_calibration_params",
    "is_final_qc",
]


def build_production(final: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in PRODUCTION_COLUMNS if c in final.columns]
    return final[cols].sort_values(["sensor_id", "timestamp"]).reset_index(drop=True)
