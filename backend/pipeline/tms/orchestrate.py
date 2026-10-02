"""Top-level orchestration for the TOMST TMS-4 pipeline: load -> continuity
-> metadata -> initial QC -> correction -> calibration -> final QC ->
production.

Each stage is cached independently on disk (see pipeline.store.stage), keyed
on its own upstream Parquet input(s) + its own parameters (including the
small in-memory config tables - metadata/correction/calibration/field_events -
hashed via their row content since they aren't file-backed). A manually
logged field event or a correction-parameter tweak only recomputes the
stages that actually depend on it, not the whole pipeline from raw data.

Returns a lazily-resolved dict of {stage_name: Path} (see store.LazyDict) -
a stage's store.stage() call (and everything it depends on) only actually
runs the first time its output is accessed. Landing on the "Metadata" step,
which only reads r["merged"]/r["with_metadata"], must not also compute
initial QC/correction/calibration/final QC/production - those steps haven't
even been reached yet.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from .. import store
from .calibration import apply_calibration
from .continuity import detect_gaps, merge_and_dedupe
from .correction import apply_correction
from .final_qc import detect_final_qc
from .initial_qc import detect_initial_qc
from .metadata import apply_metadata
from .production import build_production


def _records(df: pd.DataFrame) -> list:
    return df.to_dict("records") if df is not None and not df.empty else []


STAGE_LABELS = {
    "merged": "Merging & deduplicating raw downloads",
    "gap_report": "Detecting continuity gaps",
    "with_metadata": "Applying deployment metadata",
    "initial_qc": "Running initial QC (Hampel/flatline/range/rate per channel)",
    "corrected": "Applying signal correction",
    "calibrated": "Applying VWC calibration",
    "final": "Running final QC",
    "production": "Building the production dataset",
}


def process_tms_pipeline(pipeline_dir: Path, raw_paths: list, metadata_df: pd.DataFrame,
                          correction_params: pd.DataFrame, calibration_params: pd.DataFrame,
                          field_events: pd.DataFrame = None, qc_cfg: dict = None,
                          final_qc_cfg: dict = None, step_min: int = None, progress=None) -> dict:
    """`progress(label)`, if given, is called with a human-readable label
    right before a stage that's actually recomputing (never on a cache hit) -
    lets the caller show live progress instead of the page just sitting
    there for however long a stage takes."""
    d = Path(pipeline_dir)
    on_compute = (lambda name: progress(STAGE_LABELS.get(name, name))) if progress else None

    # Each stage is a zero-arg function, `functools.cache`-memoized so
    # multiple external keys that share one underlying store.stage() call
    # (e.g. "merged"/"dup_report") - or a downstream stage pulling the same
    # upstream one twice - only run/look up that stage once per pipeline
    # call. Not computed at all unless something actually calls it.

    @lru_cache(maxsize=None)
    def merged():
        return store.stage(
            d, "merged", raw_paths, {},
            lambda: dict(zip(("main", "dup_report"), merge_and_dedupe(store.read_df(raw_paths)))),
            on_compute=on_compute,
        )

    @lru_cache(maxsize=None)
    def gap_report():
        return store.stage(
            d, "gap_report", [merged()["main"]], {"step_min": step_min},
            lambda: detect_gaps(store.read_df(merged()["main"]), step_min),
            on_compute=on_compute,
        )

    @lru_cache(maxsize=None)
    def with_metadata():
        return store.stage(
            d, "with_metadata", [merged()["main"]], {"metadata": _records(metadata_df)},
            lambda: dict(zip(("main", "excluded"), apply_metadata(store.read_df(merged()["main"]), metadata_df))),
            on_compute=on_compute,
        )

    @lru_cache(maxsize=None)
    def initial_qc():
        return store.stage(
            d, "initial_qc", [with_metadata()["main"]], {"qc_cfg": qc_cfg or {}, "field_events": _records(field_events)},
            lambda: detect_initial_qc(store.read_df(with_metadata()["main"]), qc_cfg, field_events),
            on_compute=on_compute,
        )

    @lru_cache(maxsize=None)
    def corrected():
        return store.stage(
            d, "corrected", [initial_qc()["main"]], {"correction_params": _records(correction_params)},
            lambda: apply_correction(store.read_df(initial_qc()["main"]), correction_params),
            on_compute=on_compute,
        )

    @lru_cache(maxsize=None)
    def calibrated():
        return store.stage(
            d, "calibrated", [corrected()["main"]], {"calibration_params": _records(calibration_params)},
            lambda: apply_calibration(store.read_df(corrected()["main"]), calibration_params),
            on_compute=on_compute,
        )

    @lru_cache(maxsize=None)
    def final():
        return store.stage(
            d, "final", [calibrated()["main"]], {"final_qc_cfg": final_qc_cfg or {}, "field_events": _records(field_events)},
            lambda: detect_final_qc(store.read_df(calibrated()["main"]), final_qc_cfg, field_events),
            on_compute=on_compute,
        )

    @lru_cache(maxsize=None)
    def production():
        return store.stage(
            d, "production", [final()["main"]], {},
            lambda: build_production(store.read_df(final()["main"])),
            on_compute=on_compute,
        )

    return store.LazyDict({
        "raw_wide": lambda: raw_paths,
        "merged": lambda: merged()["main"],
        "dup_report": lambda: merged()["dup_report"],
        "gap_report": lambda: gap_report()["main"],
        "with_metadata": lambda: with_metadata()["main"],
        "excluded_metadata": lambda: with_metadata()["excluded"],
        "qc": lambda: initial_qc()["main"],
        "corrected": lambda: corrected()["main"],
        "calibrated": lambda: calibrated()["main"],
        "final": lambda: final()["main"],
        "production": lambda: production()["main"],
    })
