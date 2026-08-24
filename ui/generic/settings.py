"""Pipeline settings: defaults, persistent store, and read-back.

Each setting's *widget* lives in the sidebar (ui/sidebar.py), scoped to
whichever step is active - which means a given widget is only drawn on the
reruns where its step is selected. Streamlit forgets a widget's own state on
any rerun where that widget isn't drawn (it resets to its default the next
time it reappears), so values can't be read back via the widget's `key`.
Instead every value lives in st.session_state["settings"], a plain dict
that isn't tied to any widget's lifecycle and so survives navigating away
and back. Each widget is drawn with `value=`/`index=` from this store and
immediately writes its result back into it - and since the sidebar renders
before the pipeline runs (see app.py), that write is picked up the same
rerun, with no extra round trip.
"""
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

import pipeline.generic as P

DEFAULTS = {
    "step_min": 30,
    "use_hampel": True, "hampel_k": float(P.HAMPEL_K), "hampel_hw": P.HAMPEL_HALF_WINDOW,
    "use_flatline": True, "flatline_min_run": 6,
    "use_percentile": False, "pct_range": (0.5, 99.5),
    "use_rate": False, "rate_k": 8.0,
    "max_gap": P.MAX_INTERP_GAP,
    "use_donor_regression": P.USE_DONOR_REGRESSION, "donor_min_corr": P.DONOR_MIN_CORR,
    "smooth_method": "mean", "smooth_window": P.SMOOTH_WINDOW,
}


@dataclass
class Settings:
    step_min: int
    outlier_cfg: dict
    max_gap: int
    use_donor_regression: bool
    donor_min_corr: float
    smooth_method: str
    smooth_window: int


def init_settings() -> None:
    """Seeds the settings store exactly once, before any step's parameter
    widgets or the pipeline itself reads from it - so a step that hasn't been
    visited yet still contributes a sane default."""
    st.session_state.setdefault("settings", dict(DEFAULTS))


def store() -> dict:
    """The persistent settings dict step widgets read their current value
    from and write their new value back into."""
    return st.session_state.settings


def is_dirty() -> bool:
    """Whether this pipeline holds anything a mode switch would discard:
    tuned parameters, an uploaded file, or manual-validation overrides -
    see ui.mode's confirmation prompt before tearing a mode's state down."""
    return (
        st.session_state.get("settings", DEFAULTS) != DEFAULTS
        or bool(st.session_state.get("manual_overrides"))
        or bool(st.session_state.get("data_source_uploaded_files"))
        or bool(st.session_state.get("data_source_units_file"))
    )


def reset() -> None:
    """Drops this pipeline back to a freshly-opened state - used by ui.mode
    when switching away, so a stale settings/upload doesn't linger in
    session_state for a pipeline nobody's looking at."""
    st.session_state.settings = dict(DEFAULTS)
    st.session_state.manual_overrides = {}
    for key in ("data_source_uploaded_files", "data_source_channels", "data_source_units_file"):
        st.session_state.pop(key, None)


def get_settings() -> Settings:
    """Assembles the current value of every setting into a Settings object,
    for the pipeline run."""
    s = store()
    outlier_cfg = {
        "use_hampel": s["use_hampel"], "hampel_half_window": s["hampel_hw"], "hampel_k": s["hampel_k"],
        "use_flatline": s["use_flatline"], "flatline_min_run": s["flatline_min_run"],
        "use_percentile": s["use_percentile"], "pct_low": s["pct_range"][0], "pct_high": s["pct_range"][1],
        "use_rate": s["use_rate"], "rate_k": s["rate_k"],
    }
    return Settings(
        step_min=s["step_min"], outlier_cfg=outlier_cfg, max_gap=s["max_gap"],
        use_donor_regression=s["use_donor_regression"], donor_min_corr=s["donor_min_corr"],
        smooth_method=s["smooth_method"], smooth_window=s["smooth_window"],
    )
