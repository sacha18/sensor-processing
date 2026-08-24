"""Top-level orchestration for the TOMST TMS-4 pipeline: load -> continuity
-> metadata -> initial QC -> correction -> calibration -> final QC ->
production. Parallel to, and independent from, pipeline/orchestrate.py's
generic single-value pipeline.
"""
from __future__ import annotations

import pandas as pd

from .calibration import apply_calibration
from .continuity import detect_gaps, merge_and_dedupe
from .correction import apply_correction
from .final_qc import detect_final_qc
from .initial_qc import detect_initial_qc
from .metadata import apply_metadata
from .production import build_production


def process_tms_pipeline(raw_wide: pd.DataFrame, metadata_df: pd.DataFrame,
                          correction_params: pd.DataFrame, calibration_params: pd.DataFrame,
                          field_events: pd.DataFrame = None, qc_cfg: dict = None,
                          final_qc_cfg: dict = None, step_min: int = None) -> dict:
    merged, dup_report = merge_and_dedupe(raw_wide)
    gap_report = detect_gaps(merged, step_min)
    with_metadata, excluded_metadata = apply_metadata(merged, metadata_df)
    qc = detect_initial_qc(with_metadata, qc_cfg, field_events)
    corrected = apply_correction(qc, correction_params)
    calibrated = apply_calibration(corrected, calibration_params)
    final = detect_final_qc(calibrated, final_qc_cfg, field_events)
    production = build_production(final)

    return {
        "raw_wide": raw_wide,
        "merged": merged,
        "dup_report": dup_report,
        "gap_report": gap_report,
        "with_metadata": with_metadata,
        "excluded_metadata": excluded_metadata,
        "qc": qc,
        "corrected": corrected,
        "calibrated": calibrated,
        "final": final,
        "production": production,
    }
