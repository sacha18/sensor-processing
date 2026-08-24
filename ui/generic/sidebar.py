"""Sidebar: the active step's own parameters, scoped to whichever step is
selected in the top nav (ui/generic/nav.py) - so tweaking a value and watching the
chart react doesn't require leaving the sidebar. This runs before the
pipeline (see app.py), so a change here reaches the pipeline on the very
same rerun - no extra round trip needed.

Plain widgets, no card/badge styling - the sidebar is narrow and simple
toggles/sliders read better there than boxed tiles.
"""
from __future__ import annotations

import streamlit as st

from ui.generic.nav import STEP_NAMES
from ui.generic.settings import store


def render_sidebar(step: int) -> None:
    with st.sidebar:
        st.header("Parameters")
        st.caption(f"**{step + 1}. {STEP_NAMES[step]}**")

        s = store()
        renderer = _RENDERERS.get(step)
        if renderer is None:
            st.caption("This step has no parameters of its own.")
        else:
            renderer(s)


def _regularize_params(s: dict) -> None:
    s["step_min"] = st.selectbox("Nominal time step (min)", [15, 30, 60], index=[15, 30, 60].index(s["step_min"]),
                                  help="Every sensor's readings are snapped onto one shared grid at this interval "
                                       "before anything downstream runs.")


def _outlier_params(s: dict) -> None:
    st.caption("Independent methods, each catching a different fault mode - a point is dropped if ANY enabled "
               "method flags it.")

    s["use_hampel"] = st.toggle("Spike filter (Hampel)", value=s["use_hampel"],
                                 help="Flags a point that deviates by more than k x MAD from the median of a local window. "
                                      "A slow multi-step ramp stays inside the window's spread and is not flagged; an isolated spike is.")
    s["hampel_k"] = st.slider("MAD threshold", 3.0, 10.0, s["hampel_k"], 0.5, disabled=not s["use_hampel"])
    s["hampel_hw"] = st.slider("Window (points each side)", 2, 10, s["hampel_hw"], disabled=not s["use_hampel"])
    st.divider()

    s["use_flatline"] = st.toggle("Flatline / stuck sensor", value=s["use_flatline"],
                                   help="Flags a run of back-to-back identical readings - a fault the Hampel filter can't see "
                                        "(a flatline has zero local spread, so it never looks like a spike).")
    s["flatline_min_run"] = st.slider("Min identical readings in a row", 3, 20, s["flatline_min_run"], disabled=not s["use_flatline"])
    st.divider()

    s["use_percentile"] = st.toggle("Extreme-value bounds (percentile)", value=s["use_percentile"],
                                     help="Flags readings outside this sensor's own [low, high] percentile range - a context-free "
                                          "sanity bound (catches e.g. a sign flip or decimal-point glitch).")
    s["pct_range"] = st.slider("Keep percentile range", 0.0, 100.0, s["pct_range"], disabled=not s["use_percentile"])
    st.divider()

    s["use_rate"] = st.toggle("Rate-of-change (max jump)", value=s["use_rate"],
                               help="Flags a step whose jump exceeds k x this sensor's typical step size. Self-calibrating, "
                                    "but has no window context, so genuine rapid ramps get flagged too - opt-in only.")
    s["rate_k"] = st.slider("Jump threshold (x typical step)", 2.0, 20.0, s["rate_k"], disabled=not s["use_rate"])


def _gapfill_params(s: dict) -> None:
    s["max_gap"] = st.slider("Max gap linearly interpolated (steps)", 1, 12, s["max_gap"])
    st.caption("Beyond this many missing steps, filling switches to regression against the most correlated sensor (\"donor\").")
    st.divider()

    s["use_donor_regression"] = st.toggle("Imputation via correlated time series", value=s["use_donor_regression"],
                                           help="Fills a value by linear regression against the most correlated sensor (\"donor\"), "
                                                "fit on timestamps where both are observed. Applied straight away to outliers "
                                                "(a same-timestamp correlated reading beats interpolating neighbours), and to any "
                                                "gap left over once the interpolation limit above is exceeded.")
    s["donor_min_corr"] = st.slider("Min |correlation| required to trust a donor", 0.0, 1.0, s["donor_min_corr"], 0.05,
                                     disabled=not s["use_donor_regression"],
                                     help="Below this threshold the \"most correlated\" sensor still isn't correlated enough to "
                                          "regress on - those points fall back to interpolation/unfilled instead.")


def _smoothing_params(s: dict) -> None:
    s["smooth_method"] = st.selectbox("Smoothing method", ["mean", "median"],
                                       index=["mean", "median"].index(s["smooth_method"]))
    s["smooth_window"] = st.slider("Smoothing window (steps, centered)", 1, 21, s["smooth_window"], step=2)
    st.caption("A rolling average/median laid over the cleaned series to show trend without high-frequency noise - "
               "shown alongside, not instead of, the cleaned data. The interactive aggregation period above it on "
               "the page has its own, independent control.")


_RENDERERS = {
    2: _regularize_params,
    3: _outlier_params,
    4: _gapfill_params,
    6: _smoothing_params,
}
