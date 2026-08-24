"""Top-level pipeline mode switch: the generic single-value pipeline vs the
TOMST TMS-4 soil-sensor workflow. Two independent tracks (ui/generic/* vs
ui/tms/*, ...) sharing only the page chrome in app.py - the TMS raw
format and its metadata/correction/calibration/cross-channel QC stages have
no equivalent in the generic pipeline, so this has to be a top-level switch
rather than a per-sensor label.

Switching modes tears the mode being left down (settings/tables/uploads back
to fresh, its step position reset, its cached pipeline result cleared) rather
than leaving it initialized in the background - a pipeline nobody's looking
at shouldn't keep a multi-hundred-row cache_data entry (and everything it was
keyed on) resident. Because that's destructive, a mode switch away from a
pipeline that's been touched (tuned parameters, an upload, manual
validations, ...) is gated behind a confirmation dialog; switching from an
untouched pipeline (still at its defaults) applies immediately.
"""
from __future__ import annotations

import streamlit as st

from ui.fullscreen import exit_fullscreen
from ui.generic.data_source import get_pipeline
from ui.generic.settings import is_dirty as generic_is_dirty
from ui.generic.settings import reset as reset_generic_settings
from ui.tms.config import is_dirty as tms_config_is_dirty
from ui.tms.config import reset as reset_tms_config
from ui.tms.data_source import get_tms_pipeline
from ui.tms.settings import is_dirty as tms_settings_is_dirty
from ui.tms.settings import reset as reset_tms_settings

MODES = ["generic", "tms"]
MODE_LABELS = {"generic": "Generic pipeline", "tms": "TOMST TMS-4 (soil)"}

# gate_section keys each mode's before/after validation uses (ui.step_validate) -
# see GENERIC_STEP_GATES/TMS_STEP_GATES in app.py, the values these come from.
_GATE_SECTIONS = {"generic": ("outliers", "gapfill"), "tms": ("tms_correction", "tms_calibration", "tms_final_qc")}
_STEP_SESSION_KEY = {"generic": "step_idx", "tms": "tms_step_idx"}

_SELECTOR_KEY = "app_mode_selector"
_PENDING_KEY = "app_mode_pending_switch"
_SYNC_FLAG = "app_mode_selector_needs_sync"


def init_mode() -> None:
    st.session_state.setdefault("app_mode", "generic")


def _is_dirty(mode: str) -> bool:
    if mode == "tms":
        return tms_settings_is_dirty() or tms_config_is_dirty() or bool(st.session_state.get("tms_uploaded_files"))
    return generic_is_dirty()


def _shut_down(mode: str) -> None:
    """Tears `mode` down to a freshly-opened state and drops its cached
    pipeline result - called right before switching away from it."""
    if mode == "tms":
        reset_tms_settings()
        reset_tms_config()
        st.session_state.pop("tms_uploaded_files", None)
        get_tms_pipeline.clear()
    else:
        reset_generic_settings()
        get_pipeline.clear()

    step_key = _STEP_SESSION_KEY[mode]
    st.session_state[step_key] = 0
    st.session_state[f"{step_key}_unlocked"] = 0
    for section in _GATE_SECTIONS[mode]:
        st.session_state.get("step_validated", {}).pop(section, None)
    exit_fullscreen()


def _cancel_pending_switch() -> None:
    st.session_state[_PENDING_KEY] = None
    st.session_state[_SYNC_FLAG] = True  # hold the control at `current` once the widget redraws next run


@st.dialog("Switch pipeline?", on_dismiss=_cancel_pending_switch)
def _confirm_switch_dialog(current: str, target: str) -> None:
    st.write(f"You've made changes on the **{MODE_LABELS[current]}** pipeline (tuned parameters, an upload, or "
             f"manual validations) that aren't saved anywhere else. Switching to **{MODE_LABELS[target]}** now "
             "discards them.")
    c1, c2 = st.columns(2)
    if c1.button("Cancel", width="stretch"):
        _cancel_pending_switch()
        st.rerun()
    if c2.button("Discard changes & switch", type="primary", width="stretch"):
        _shut_down(current)
        st.session_state.app_mode = target
        st.session_state[_PENDING_KEY] = None
        st.session_state[_SYNC_FLAG] = True  # move the control onto `target` once the widget redraws next run
        st.rerun()


def render_mode_switch() -> str:
    current = st.session_state.app_mode or "generic"

    # A widget-bound session_state key can't be written after that widget has
    # already been instantiated this run (Streamlit raises on it) - so a
    # forced reset onto `current` (after Cancel, or after Confirm changed
    # `current` itself) has to be applied *before* the segmented_control call
    # below, one rerun after the decision was made, not inside the decision's
    # own click handler.
    if st.session_state.pop(_SYNC_FLAG, False):
        st.session_state[_SELECTOR_KEY] = current
    else:
        st.session_state.setdefault(_SELECTOR_KEY, current)

    selected = st.segmented_control("Pipeline", MODES, key=_SELECTOR_KEY, format_func=lambda m: MODE_LABELS[m])
    selected = selected or current  # segmented_control allows de-selecting to None

    pending = st.session_state.get(_PENDING_KEY)
    if pending is not None:
        # A confirmation is already in flight - keep showing it regardless of
        # what `selected` reads as right now (still the un-applied target
        # click), rather than reinterpreting it as a fresh switch attempt.
        _confirm_switch_dialog(current, pending)
        return current

    if selected == current:
        return current

    if _is_dirty(current):
        st.session_state[_PENDING_KEY] = selected
        _confirm_switch_dialog(current, selected)
        return current

    _shut_down(current)
    st.session_state.app_mode = selected
    return selected
