"""Top-level orchestration: load -> dedupe -> regularize -> outliers ->
similarity -> gap fill -> production dataset -> aggregation/smoothing.

Each stage is cached independently on disk (see pipeline.store.stage), keyed
on its own upstream Parquet input(s) + its own parameters - changing e.g. the
smoothing window only recomputes `smoothed_wide`, not dedupe/regularize/
outliers/similarity/gap-fill upstream of it.

Returns a lazily-resolved dict of {stage_name: Path} (see store.LazyDict) -
a stage's store.stage() call (and everything it depends on) only actually
runs the first time its output is accessed, so landing on an early step
(e.g. "Deduplication") doesn't also compute similarity/gap-fill/aggregation/
smoothing that step never reads.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .. import store
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
from .io import write_raw_dir_to_store
from .outliers import detect_outliers
from .postprocess import aggregate, smooth
from .regularize import regularize
from .similarity import similarity


STAGE_LABELS = {
    "deduped": "Deduplicating readings",
    "regularized": "Regularizing onto a fixed time grid",
    "qc": "Detecting outliers",
    "sim": "Computing sensor similarity",
    "gapfill": "Filling gaps",
    "production_wide": "Pivoting to wide format",
    "agg": "Aggregating",
    "smoothed_wide": "Smoothing",
}


def process_pipeline(pipeline_dir: Path, raw_paths: list, step_min: int = STEP_MIN,
                      outlier_cfg: dict = None, max_interp_gap: int = MAX_INTERP_GAP,
                      agg_freq: str = AGG_FREQ, smooth_window: int = SMOOTH_WINDOW,
                      smooth_method: str = SMOOTH_METHOD,
                      use_donor_regression: bool = USE_DONOR_REGRESSION,
                      donor_min_corr: float = DONOR_MIN_CORR, progress=None) -> dict:
    """Runs dedupe -> ... -> production -> aggregation/smoothing on the raw
    Parquet parts at `raw_paths` (from io.write_raw_dir_to_store /
    write_raw_uploads_to_store), staging each step's output under
    `pipeline_dir`. Returns a lazy {stage_name: Path} dict.

    `progress(label)`, if given, is called with a human-readable label right
    before a stage that's actually recomputing (never on a cache hit) - lets
    the caller show live progress instead of the page just sitting there."""
    d = Path(pipeline_dir)
    on_compute = (lambda name: progress(STAGE_LABELS.get(name, name))) if progress else None

    # Each stage is a zero-arg function, `functools.cache`-memoized so
    # multiple external keys sharing one store.stage() call (e.g.
    # "deduped"/"dup_report"), or a downstream stage pulling the same
    # upstream one twice, only run/look up that stage once per pipeline
    # call - and not at all unless something actually calls it.

    @lru_cache(maxsize=None)
    def deduped():
        return store.stage(
            d, "deduped", raw_paths, {},
            lambda: dict(zip(("main", "dup_report"), dedupe(store.read_df(raw_paths)))),
            on_compute=on_compute,
        )

    @lru_cache(maxsize=None)
    def regularized():
        def _compute():
            reg, span, grid = regularize(store.read_df(deduped()["main"]), step_min)
            return {"main": reg, "span": span.reset_index(), "grid": grid.to_frame(index=False, name="timestamp")}
        return store.stage(d, "regularized", [deduped()["main"]], {"step_min": step_min}, _compute,
                            on_compute=on_compute)

    @lru_cache(maxsize=None)
    def qc():
        return store.stage(
            d, "qc", [regularized()["main"]], {"outlier_cfg": outlier_cfg or {}},
            lambda: detect_outliers(store.read_df(regularized()["main"]), outlier_cfg),
            on_compute=on_compute,
        )

    @lru_cache(maxsize=None)
    def sim():
        return store.stage(
            d, "sim", [qc()["main"]], {},
            lambda: similarity(store.read_df(qc()["main"])),
            on_compute=on_compute,
        )

    @lru_cache(maxsize=None)
    def gapfill():
        def _compute():
            qc_df = store.read_df(qc()["main"])
            sim_dict = store.load_pickle(sim()["main"])
            production, stage1, method1 = gap_fill(qc_df, sim_dict, max_interp_gap, use_donor_regression, donor_min_corr)
            return {"main": production, "stage1": stage1.reset_index(), "method1": method1.reset_index()}
        gap_params = {"max_interp_gap": max_interp_gap, "use_donor_regression": use_donor_regression,
                      "donor_min_corr": donor_min_corr}
        return store.stage(d, "gapfill", [qc()["main"], sim()["main"]], gap_params, _compute, on_compute=on_compute)

    @lru_cache(maxsize=None)
    def production_wide():
        return store.stage(
            d, "production_wide", [gapfill()["main"]], {},
            lambda: store.read_df(gapfill()["main"])
            .pivot(index="timestamp", columns="sensor_id", values="value_clean").sort_index().reset_index(),
            on_compute=on_compute,
        )

    @lru_cache(maxsize=None)
    def agg():
        return store.stage(
            d, "agg", [gapfill()["main"]], {"agg_freq": agg_freq},
            lambda: aggregate(store.read_df(gapfill()["main"]), agg_freq),
            on_compute=on_compute,
        )

    @lru_cache(maxsize=None)
    def smoothed_wide():
        smooth_params = {"smooth_window": smooth_window, "smooth_method": smooth_method}
        return store.stage(
            d, "smoothed_wide", [production_wide()["main"]], smooth_params,
            lambda: smooth(store.read_df(production_wide()["main"]).set_index("timestamp"), smooth_window, smooth_method)
            .reset_index(),
            on_compute=on_compute,
        )

    return store.LazyDict({
        "raw_long": lambda: raw_paths,
        "deduped": lambda: deduped()["main"],
        "dup_report": lambda: deduped()["dup_report"],
        "reg_long": lambda: regularized()["main"],
        "span": lambda: regularized()["span"],
        "grid": lambda: regularized()["grid"],
        "qc_long": lambda: qc()["main"],
        "sim": lambda: sim()["main"],
        "production": lambda: gapfill()["main"],
        "production_wide": lambda: production_wide()["main"],
        "agg": lambda: agg()["main"],
        "smoothed_wide": lambda: smoothed_wide()["main"],
    })


def run_pipeline(pipeline_dir: Path, data_dir: Path = None, step_min: int = STEP_MIN,
                  outlier_cfg: dict = None, max_interp_gap: int = MAX_INTERP_GAP) -> dict:
    """Convenience wrapper: write_raw_dir_to_store(data_dir) then process_pipeline(...)."""
    pipeline_dir = Path(pipeline_dir)
    raw_paths = write_raw_dir_to_store(pipeline_dir / "raw", data_dir)
    return process_pipeline(pipeline_dir, raw_paths, step_min, outlier_cfg, max_interp_gap)
