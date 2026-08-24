"""Generic sensor data pipeline: load -> dedupe -> regularize -> outliers ->
similarity -> gap fill -> production dataset.

Works on any folder of `<sensor_id>.json` or `<sensor_id>.csv` files, each a
list/table of observations with `phenomenon_time` and `result` columns
(`observation_id` optional) - a CSV is just the JSON schema's fields as a
table instead of a list of dicts, same required columns either way. Sensor
count, names, ranges and native sampling rate are all discovered from the
data - none of it is hardcoded to a particular deployment.

Pure pandas/numpy/scipy logic, no UI here - app.py (Streamlit) drives it and
displays each phase. Split into submodules by pipeline stage; this file
re-exports the public API so `import pipeline.generic as P` behaves like
`import pipeline.tms as TMS` does for the TMS pipeline.
"""
from __future__ import annotations

from .config import (
    AGG_FREQ,
    DEFAULT_OUTLIER_CFG,
    DONOR_MIN_CORR,
    ENV_DATA_DIR,
    HAMPEL_HALF_WINDOW,
    HAMPEL_K,
    MAX_INTERP_GAP,
    SAMPLE_DATA_DIR,
    SMOOTH_METHOD,
    SMOOTH_WINDOW,
    STEP_MIN,
    SUPPORTED_EXTENSIONS,
    USE_DONOR_REGRESSION,
)
from .dedupe import dedupe
from .gapfill import donor_fill, fit_donor_regression, gap_fill, interp_short_gaps
from .io import load_raw, load_raw_from_uploads, parse_units_mapping, resolve_data_dir
from .orchestrate import process_pipeline, run_pipeline
from .outliers import detect_outliers, flatline_flags, hampel_flags, percentile_flags, rate_flags
from .postprocess import aggregate, smooth
from .regularize import regularize
from .similarity import similarity

__all__ = [
    "AGG_FREQ", "DEFAULT_OUTLIER_CFG", "DONOR_MIN_CORR", "ENV_DATA_DIR",
    "HAMPEL_HALF_WINDOW", "HAMPEL_K", "MAX_INTERP_GAP", "SAMPLE_DATA_DIR",
    "SMOOTH_METHOD", "SMOOTH_WINDOW", "STEP_MIN", "SUPPORTED_EXTENSIONS",
    "USE_DONOR_REGRESSION",
    "dedupe", "donor_fill", "fit_donor_regression", "gap_fill", "interp_short_gaps",
    "load_raw", "load_raw_from_uploads", "parse_units_mapping", "resolve_data_dir",
    "process_pipeline", "run_pipeline",
    "detect_outliers", "flatline_flags", "hampel_flags", "percentile_flags", "rate_flags",
    "aggregate", "smooth",
    "regularize",
    "similarity",
]
