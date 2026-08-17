"""Top-level orchestration: load -> dedupe -> regularize -> outliers ->
similarity -> gap fill -> production dataset -> aggregation/smoothing.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import (
    AGG_FREQ,
    DONOR_MIN_CORR,
    MAX_INTERP_GAP,
    SMOOTH_METHOD,
    SMOOTH_WINDOW,
    STEP_MIN,
    USE_DONOR_REGRESSION,
)
from .dedupe import dedupe
from .gapfill import gap_fill
from .io import load_raw
from .outliers import detect_outliers
from .postprocess import aggregate, smooth
from .regularize import regularize
from .similarity import similarity


def process_pipeline(raw_long: pd.DataFrame, step_min: int = STEP_MIN,
                      outlier_cfg: dict = None, max_interp_gap: int = MAX_INTERP_GAP,
                      agg_freq: str = AGG_FREQ, smooth_window: int = SMOOTH_WINDOW,
                      smooth_method: str = SMOOTH_METHOD,
                      use_donor_regression: bool = USE_DONOR_REGRESSION,
                      donor_min_corr: float = DONOR_MIN_CORR) -> dict:
    """Run dedupe -> ... -> production -> aggregation/smoothing on an already-loaded
    raw_long frame (from load_raw or load_raw_from_uploads)."""
    deduped, dup_report = dedupe(raw_long)
    reg_long, span, grid = regularize(deduped, step_min)
    qc_long = detect_outliers(reg_long, outlier_cfg)
    sim = similarity(qc_long)
    production, stage1, method1 = gap_fill(qc_long, sim, max_interp_gap, use_donor_regression, donor_min_corr)
    production_wide = production.pivot(index="timestamp", columns="sensor_id", values="value_clean").sort_index()
    agg = aggregate(production, agg_freq)
    smoothed_wide = smooth(production_wide, smooth_window, smooth_method)

    return {
        "raw_long": raw_long,
        "deduped": deduped,
        "dup_report": dup_report,
        "reg_long": reg_long,
        "span": span,
        "grid": grid,
        "qc_long": qc_long,
        "sim": sim,
        "production": production,
        "production_wide": production_wide,
        "agg": agg,
        "smoothed_wide": smoothed_wide,
    }


def run_pipeline(data_dir: Path = None, step_min: int = STEP_MIN,
                  outlier_cfg: dict = None, max_interp_gap: int = MAX_INTERP_GAP) -> dict:
    """Convenience wrapper: load_raw(data_dir) then process_pipeline(...)."""
    raw_long = load_raw(data_dir)
    return process_pipeline(raw_long, step_min, outlier_cfg, max_interp_gap)
