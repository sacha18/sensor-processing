"""Sidebar for the TMS workflow - mirrors ui/generic/sidebar.py's
per-step-scoped pattern (each step's own parameters, drawn only while that
step is active), against ui.tms.settings's store instead of
ui.generic.settings's.
"""
from __future__ import annotations

import streamlit as st

from pipeline.tms.config import SIGNAL_CHANNELS
from ui.tms.nav import TMS_STEP_NAMES
from ui.tms.settings import store


def render_sidebar_tms(step: int) -> None:
    with st.sidebar:
        st.header("Parameters")
        st.caption(f"**{step + 1}. {TMS_STEP_NAMES[step]}**")

        s = store()
        renderer = _RENDERERS.get(step)
        if renderer is None:
            st.caption("This step has no parameters of its own.")
        else:
            renderer(s)


def _continuity_params(s: dict) -> None:
    auto = st.toggle("Auto-detect sampling step", value=s["step_min"] is None,
                      help="Infers each sensor's own nominal logging interval from the modal gap between its "
                           "timestamps, rather than assuming one fixed interval for every sensor.")
    if auto:
        s["step_min"] = None
    else:
        options = [15, 30, 60]
        s["step_min"] = st.selectbox("Nominal step (min)", options, index=options.index(s["step_min"] or 15))
    st.caption("Used to decide what counts as a gap in the continuity report - a delta more than 1.5x this step.")


def _initial_qc_params(s: dict) -> None:
    channel = st.selectbox("Channel", SIGNAL_CHANNELS, format_func=str.upper,
                            help="T1/T2/T3/Signal are QC'd independently - a problem on one channel doesn't flag the others.")
    c = s["qc_cfg"][channel]
    st.caption("Independent methods, each catching a different fault mode - a point is dropped if ANY enabled "
               "method flags it.")

    c["use_hampel"] = st.toggle("Spike filter (Hampel)", value=c["use_hampel"])
    c["hampel_k"] = st.slider("MAD threshold", 3.0, 10.0, float(c["hampel_k"]), 0.5, disabled=not c["use_hampel"])
    c["hampel_half_window"] = st.slider("Window (points each side)", 2, 10, c["hampel_half_window"], disabled=not c["use_hampel"])
    st.divider()

    c["use_flatline"] = st.toggle("Flatline / stuck sensor", value=c["use_flatline"],
                                   help="TMS channels are slow-changing, logged every ~15 min - the default run "
                                        "length is tuned so ordinary overnight plateaus aren't flagged.")
    c["flatline_min_run"] = st.slider("Min identical readings in a row", 3, 200, c["flatline_min_run"], disabled=not c["use_flatline"])
    st.divider()

    c["use_percentile"] = st.toggle("Extreme-value bounds (percentile)", value=c["use_percentile"])
    c["pct_low"], c["pct_high"] = st.slider("Keep percentile range", 0.0, 100.0, (c["pct_low"], c["pct_high"]), disabled=not c["use_percentile"])
    st.divider()

    c["use_rate"] = st.toggle("Rate-of-change (max jump)", value=c["use_rate"])
    c["rate_k"] = st.slider("Jump threshold (x typical step)", 2.0, 20.0, float(c["rate_k"]), disabled=not c["use_rate"])


def _final_qc_params(s: dict) -> None:
    c = s["final_qc_cfg"]
    c["vwc_min"], c["vwc_max"] = st.slider("Plausible VWC range", 0.0, 1.0, (c["vwc_min"], c["vwc_max"]), 0.01)
    c["freeze_threshold_c"] = st.slider(
        "Freeze threshold (T1, °C)", -10.0, 10.0, float(c["freeze_threshold_c"]), 0.5,
        help="Below this T1 reading, soil is assumed frozen and Signal/VWC are flagged - freezing changes the "
             "dielectric response the sensor relies on to measure moisture.")
    st.divider()
    c["use_flatline"] = st.toggle("VWC flatline / stuck", value=c["use_flatline"])
    c["flatline_min_run"] = st.slider("Min identical VWC readings in a row", 3, 200, c["flatline_min_run"], disabled=not c["use_flatline"])


_RENDERERS = {
    0: _continuity_params,
    2: _initial_qc_params,
    5: _final_qc_params,
}
