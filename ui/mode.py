"""Top-level pipeline mode switch: the generic single-value pipeline vs the
TOMST TMS-4 soil-sensor workflow. Two independent tracks (ui/generic/* vs
ui/tms/*, ...) sharing only the page chrome in app.py - the TMS raw
format and its metadata/correction/calibration/cross-channel QC stages have
no equivalent in the generic pipeline, so this has to be a top-level switch
rather than a per-sensor label.
"""
from __future__ import annotations

import streamlit as st

MODES = ["generic", "tms"]
MODE_LABELS = {"generic": "Generic pipeline", "tms": "TOMST TMS-4 (soil)"}


def init_mode() -> None:
    st.session_state.setdefault("app_mode", "generic")


def render_mode_switch() -> str:
    st.segmented_control("Pipeline", MODES, key="app_mode", format_func=lambda m: MODE_LABELS[m])
    return st.session_state.app_mode or "generic"  # segmented_control allows de-selecting to None
