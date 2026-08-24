"""Shared constants and defaults for the TOMST TMS-4 pipeline."""
from __future__ import annotations

import re

# TOMST export naming: data_<sensor serial>_<yyyy>_<mm>_<dd>_<download part>.csv
FILENAME_RE = re.compile(r"data_(\d+)_(\d{4})_(\d{2})_(\d{2})_(\d+)\.csv$", re.IGNORECASE)
# TOMST's export tool emits any of these depending on the logger's regional
# settings - tried in order, row by row, in parse_tms_records. The date-only
# form shows up when a file has been resaved in Excel, which drops a
# 00:00:00 time-of-day when formatting a date cell.
TIMESTAMP_FORMATS = ["%Y.%m.%d %H:%M", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y"]
# raw field order (V1-V10) in the semicolon-separated, headerless export.
# V1/V2/V4-V7 are the fields the processing actually uses (index, timestamp,
# T1/T2/T3, Signal); V3/V8-V10 aren't used by any processing step but are
# still parsed and carried through raw_wide/merged untouched, for archive
# fidelity - V10 in particular is just a trailing ";" on most exports (empty),
# but isn't assumed to always be, so it's preserved rather than dropped.
RAW_FIELDS = ["row_index", "timestamp_raw", "v3_raw", "t1_raw", "t2_raw", "t3_raw",
              "signal_raw", "shake", "err_flag", "v10_raw"]
# raw_wide's own column set (what parse_tms_records produces, and what the
# "Download merged raw archive CSV" button on the loading step exports) -
# used to recognize that export when it's fed back in as an upload, so a
# large multi-file session can be resumed without re-uploading every raw
# TOMST file again.
MERGED_EXPORT_COLUMNS = ["sensor_id", "source_file", "row_index", "timestamp", "v3_raw", "t1_raw",
                          "t2_raw", "t3_raw", "signal_raw", "shake", "err_flag", "v10_raw"]
CHANNELS = ["t1", "t2", "t3"]
SIGNAL_CHANNELS = [*CHANNELS, "signal"]

# TOMST TMS-4's standard near-surface installation: T1 = soil (~8cm depth),
# T2 = surface (0cm), T3 = air (~15cm above surface), Signal ~ the 0-15cm
# layer. Offered as pre-filled SUGGESTIONS in the metadata step (editable,
# never assumed by the pipeline itself) - a deeper install has different
# physical channel meanings and must override these via metadata.
NEAR_SURFACE_POSITION = "near_surface"
NEAR_SURFACE_LABELS = {"t1_label": "soil (~8cm)", "t2_label": "surface (0cm)", "t3_label": "air (~15cm)"}

DEFAULT_STEP_MIN = 15   # nominal TMS-4 logging interval, used when a sensor's own step can't be inferred
GAP_TOLERANCE = 1.5     # x nominal step before a timestamp delta counts as a gap
ERR_FLAG_OK = 0

# physically plausible bounds - placeholders, tune to the real deployment/soil type
VWC_MIN = 0.0
VWC_MAX = 0.60
FREEZE_THRESHOLD_C = 1.0  # below this, T1 (soil) freezing makes Signal/VWC dielectric response unreliable

CORRECTION_TYPES = ["one_factor", "two_factor"]
MAX_POLY_DEGREE = 5
POLY_COEF_COLUMNS = [f"coef_{i}" for i in range(MAX_POLY_DEGREE + 1)]

# TOMST's own published universal calibration (quadratic in corrected Signal) -
# not sensor-specific, offered as a one-click default in the calibration step
# (a sensor_id="*" row) rather than hardcoded into apply_calibration, since
# calibration must stay assignable through metadata, not baked into the code.
TOMST_UNIVERSAL_CALIBRATION = {"coef_0": -0.101168511, "coef_1": 0.000118119, "coef_2": 0.000000017}

DEFAULT_TMS_QC_CFG = {
    # flatline_min_run is much higher than the generic pipeline's default (6): TMS
    # channels are slow-changing physical quantities logged every 15 min, so a
    # dozen back-to-back identical readings is normal weather, not a stuck sensor -
    # 48 steps (12h) is calibrated against the bundled sample data to catch genuine
    # multi-day stuck-sensor faults without flagging ordinary overnight plateaus.
    ch: {
        "use_hampel": True, "hampel_half_window": 5, "hampel_k": 6,
        "use_flatline": True, "flatline_min_run": 48,
        "use_percentile": False, "pct_low": 0.5, "pct_high": 99.5,
        "use_rate": False, "rate_k": 8.0,
    }
    for ch in SIGNAL_CHANNELS
}

DEFAULT_FINAL_QC_CFG = {
    "vwc_min": VWC_MIN, "vwc_max": VWC_MAX,
    "freeze_threshold_c": FREEZE_THRESHOLD_C,
    # same reasoning as DEFAULT_TMS_QC_CFG's flatline_min_run above - VWC is derived
    # from the equally slow-changing/quantized Signal, so it inherits the same long
    # flat runs during normal operation.
    "use_flatline": True, "flatline_min_run": 48,
}
