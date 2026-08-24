"""Shared constants and defaults for the pipeline package."""
from __future__ import annotations

import os
from pathlib import Path

STEP_MIN = 30
MAX_INTERP_GAP = 4       # steps (2h): filled by linear time-interpolation
HAMPEL_HALF_WINDOW = 5   # points each side of the tested point
HAMPEL_K = 6             # MAD multiplier -> outlier threshold
USE_DONOR_REGRESSION = True  # impute via the most correlated sensor (outliers + long gaps)
DONOR_MIN_CORR = 0.3     # |correlation| a donor must clear before it's trusted to impute
SUPPORTED_EXTENSIONS = [".json", ".csv"]

# resolution order: SENSOR_DATA_DIR env var ->
# bundled sample dataset, so the app always has something to show
ENV_DATA_DIR = os.environ.get("SENSOR_DATA_DIR")
SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "sample_data" / "generic"

DEFAULT_OUTLIER_CFG = {
    "use_hampel": True, "hampel_half_window": HAMPEL_HALF_WINDOW, "hampel_k": HAMPEL_K,
    "use_flatline": True, "flatline_min_run": 6,
    "use_percentile": False, "pct_low": 0.5, "pct_high": 99.5,
    "use_rate": False, "rate_k": 8.0,
}

AGG_FREQ = "1D"
SMOOTH_WINDOW = 5    # steps, centered
SMOOTH_METHOD = "mean"  # "mean" or "median"
