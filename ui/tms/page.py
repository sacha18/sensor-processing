"""TOMST TMS-4 pipeline page - the soil-sensor workflow (see pipeline.tms).
Locked to this page for the session once chosen from ui.picker; wires the top
nav, sidebar parameters, and data source together, then dispatches to the
ui/tms/steps/* module for whichever step is on screen - previously app.py's
job before the pipeline picker/page split.
"""
from __future__ import annotations

import streamlit as st

from ui.fullscreen import any_fullscreen, inject_chrome_hide_css
from ui.loading import loading_pending
from ui.stepper import render_stepper_controls
from ui.tms.config import init_tms_config
from ui.tms.data_source import LOADING_NAMESPACE, peek_tms_fingerprint, render_data_source_tms
from ui.tms.nav import TMS_STEP_NAMES, render_nav_tms
from ui.tms.settings import get_tms_settings, init_tms_settings
from ui.tms.sidebar import render_sidebar_tms
from ui.tms.steps import (
    analysis as tms_analysis,
    calibration as tms_calibration,
    correction as tms_correction,
    final_qc as tms_final_qc,
    initial_qc as tms_initial_qc,
    load as tms_load,
    metadata as tms_metadata,
    production as tms_production,
)

# Step indices, in the same order as TMS_STEP_NAMES - named so the dispatch
# below reads by step, not by position.
(
    STEP_LOAD, STEP_METADATA, STEP_INITIAL_QC, STEP_CORRECTION,
    STEP_CALIBRATION, STEP_FINAL_QC, STEP_ANALYSIS, STEP_PRODUCTION,
) = range(len(TMS_STEP_NAMES))

# step index -> the before/after section (ui.step_validate) that must be
# validated before the stepper's Next button unlocks the following step.
# A step not listed here has no before/after and advances freely.
STEP_GATES = {
    STEP_CORRECTION: "tms_correction",
    STEP_CALIBRATION: "tms_calibration",
    STEP_FINAL_QC: "tms_final_qc",
}


def render_tms_page(picker_page) -> None:
    init_tms_settings()
    init_tms_config()

    if any_fullscreen():
        inject_chrome_hide_css()

    with st.container(key="app_chrome"):
        col_title, col_change = st.columns([5, 1])
        with col_title:
            st.title("Sensor data processor")
        with col_change:
            st.write("")
            if st.button("Change pipeline", icon=":material/swap_horiz:", key="change_pipeline_tms",
                         width="stretch"):
                st.switch_page(picker_page)
        step = render_nav_tms()

    render_sidebar_tms(step)
    tms_settings = get_tms_settings()

    # Priming pass: a new/changed upload needs a run that paints Next as
    # disabled *before* the heavy parse/pipeline call blocks the script -
    # see ui.loading for why this can't just be a `disabled=` on the button
    # rendered after that call. This pass skips the step content and the
    # heavy work (skip_heavy=True below), then reruns itself into the pass
    # that does it - but still renders the data source's upload widget (via
    # render_data_source_tms itself), since a run that doesn't re-declare
    # a file_uploader unmounts it client-side and drops whatever was
    # attached, i.e. the very upload that triggered this pass.
    loading = loading_pending(LOADING_NAMESPACE, peek_tms_fingerprint())
    if loading:
        render_stepper_controls(step, n_steps=len(TMS_STEP_NAMES), session_key="tms_step_idx",
                                 gate_section=STEP_GATES.get(step), loading=True)

    r, sensors = render_data_source_tms(tms_settings, step == STEP_LOAD, skip_heavy=loading)

    if loading:
        st.rerun()

    if step == STEP_LOAD:
        tms_load.render(r, sensors)
    if step == STEP_METADATA:
        tms_metadata.render(r)
    if step == STEP_INITIAL_QC:
        tms_initial_qc.render(r, sensors)
    if step == STEP_CORRECTION:
        tms_correction.render(r, sensors)
    if step == STEP_CALIBRATION:
        tms_calibration.render(r, sensors)
    if step == STEP_FINAL_QC:
        tms_final_qc.render(r, sensors)
    if step == STEP_ANALYSIS:
        tms_analysis.render(r, sensors)
    if step == STEP_PRODUCTION:
        tms_production.render(r, sensors)

    render_stepper_controls(step, n_steps=len(TMS_STEP_NAMES), session_key="tms_step_idx",
                             gate_section=STEP_GATES.get(step), loading=False)
