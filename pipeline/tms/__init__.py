"""TOMST TMS-4 soil-sensor pipeline: load -> merge/continuity -> metadata ->
initial QC -> signal correction -> VWC calibration -> final QC -> production.

Parallel to, and independent from, the generic single-value pipeline in
pipeline/generic/ - see pipeline/tms/orchestrate.py::process_tms_pipeline for
the entrypoint most callers want. This file re-exports the public API so
`import pipeline.tms as TMS` behaves like `import pipeline.generic as P` does
for the generic pipeline.
"""
from __future__ import annotations

from .analysis import assign_temperature_levels, daily_group_mean, daily_stats, group_mean, resample_stats
from .calibration import apply_calibration
from .config import (
    DEFAULT_FINAL_QC_CFG,
    DEFAULT_TMS_QC_CFG,
    FREEZE_THRESHOLD_C,
    MAX_POLY_DEGREE,
    NEAR_SURFACE_LABELS,
    NEAR_SURFACE_POSITION,
    POLY_COEF_COLUMNS,
    TOMST_UNIVERSAL_CALIBRATION,
    VWC_MAX,
    VWC_MIN,
)
from .continuity import detect_gaps, infer_step_minutes, merge_and_dedupe
from .correction import apply_correction
from .events import field_event_flags
from .final_qc import detect_final_qc
from .initial_qc import detect_initial_qc
from .io import extract_sensor_id, parse_tms_records, write_tms_raw_uploads_to_store
from .metadata import METADATA_COLUMNS, apply_metadata
from .orchestrate import process_tms_pipeline
from .params import WILDCARD_KEYS, first_match, identity_mask
from .production import PRODUCTION_COLUMNS, build_production

__all__ = [
    "DEFAULT_FINAL_QC_CFG", "DEFAULT_TMS_QC_CFG", "FREEZE_THRESHOLD_C",
    "MAX_POLY_DEGREE", "METADATA_COLUMNS", "NEAR_SURFACE_LABELS", "NEAR_SURFACE_POSITION",
    "POLY_COEF_COLUMNS", "PRODUCTION_COLUMNS", "TOMST_UNIVERSAL_CALIBRATION",
    "VWC_MAX", "VWC_MIN", "WILDCARD_KEYS",
    "apply_calibration", "apply_correction", "apply_metadata", "assign_temperature_levels",
    "build_production", "daily_group_mean", "daily_stats", "detect_final_qc", "detect_gaps",
    "detect_initial_qc", "extract_sensor_id", "field_event_flags", "group_mean",
    "infer_step_minutes", "first_match", "identity_mask",
    "merge_and_dedupe", "parse_tms_records", "process_tms_pipeline", "resample_stats",
    "write_tms_raw_uploads_to_store",
]
