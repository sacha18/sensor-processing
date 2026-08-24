"""Generic pipeline page - the single-value sensor cleaning/homogenization
workflow (see pipeline.generic). Locked to this page for the session once
chosen from ui.picker; wires the top nav, sidebar parameters, data source
and manual-override commit together, then dispatches to the ui/generic/steps/*
module for whichever step is on screen - previously app.py's job before the
pipeline picker/page split.
"""
from __future__ import annotations

import streamlit as st

from ui.fullscreen import any_fullscreen, inject_chrome_hide_css
from ui.generic.data_source import LOADING_NAMESPACE, peek_generic_fingerprint, render_data_source
from ui.generic.nav import STEP_NAMES, render_nav
from ui.generic.overrides import apply_manual_overrides
from ui.generic.settings import get_settings, init_settings
from ui.generic.sidebar import render_sidebar
from ui.generic.steps import (
    analysis,
    dedupe as step_dedupe,
    gapfill as step_gapfill,
    load as step_load,
    manual_validation,
    outliers as step_outliers,
    production,
    regularize as step_regularize,
)
from ui.loading import loading_pending
from ui.stepper import render_stepper_controls

# Step indices, in the same order as STEP_NAMES - named so the dispatch below
# reads by step, not by position.
(
    STEP_LOAD, STEP_DEDUPE, STEP_REGULARIZE, STEP_OUTLIERS,
    STEP_GAPFILL, STEP_PRODUCTION, STEP_ANALYSIS,
) = range(len(STEP_NAMES))

# step index -> the before/after section (ui.step_validate) that must be
# validated before the stepper's Next button unlocks the following step.
# A step not listed here has no before/after and advances freely.
STEP_GATES = {STEP_OUTLIERS: "outliers", STEP_GAPFILL: "gapfill"}


def render_generic_page(picker_page) -> None:
    init_settings()

    if any_fullscreen():
        inject_chrome_hide_css()

    with st.container(key="app_chrome"):
        col_title, col_change = st.columns([5, 1])
        with col_title:
            st.title("Sensor data processor")
        with col_change:
            st.write("")
            if st.button("Change pipeline", icon=":material/swap_horiz:", key="change_pipeline_generic",
                         width="stretch"):
                st.switch_page(picker_page)
        step = render_nav()

    render_sidebar(step)
    settings = get_settings()

    # Priming pass: a new/changed upload needs a run that paints Next as
    # disabled *before* the heavy parse/pipeline call blocks the script -
    # see ui.loading. render_data_source still runs (skip_heavy=True) so its
    # file_uploader stays mounted - skipping it here would unmount the
    # widget and drop the very upload that triggered this pass.
    loading = loading_pending(LOADING_NAMESPACE, peek_generic_fingerprint())
    if loading:
        render_stepper_controls(step, n_steps=len(STEP_NAMES), session_key="step_idx",
                                 gate_section=STEP_GATES.get(step), loading=True)

    r, sensors, units = render_data_source(settings, step == STEP_LOAD, skip_heavy=loading)

    if loading:
        st.rerun()

    # Manual-validation overrides are applied here, unconditionally, so every step
    # (not just the Manual validation step itself) sees the committed values
    # regardless of which step is currently on screen.
    overrides_applied_count = apply_manual_overrides(r, settings.smooth_window, settings.smooth_method)

    if step == STEP_LOAD:
        step_load.render(r, units)
    if step == STEP_DEDUPE:
        step_dedupe.render(r)
    if step == STEP_REGULARIZE:
        step_regularize.render(r, settings.step_min, sensors)
    if step == STEP_OUTLIERS:
        # Detection and review live on the same screen now - no extra click
        # between spotting an outlier/gap and actually validating it.
        step_outliers.render(r, sensors, settings.use_donor_regression)
        manual_validation.render(r, sensors, overrides_applied_count)
    if step == STEP_GAPFILL:
        step_gapfill.render(r, sensors)
    if step == STEP_PRODUCTION:
        production.render(r, sensors)
    if step == STEP_ANALYSIS:
        analysis.render(r, sensors, settings.smooth_method, settings.smooth_window)

    render_stepper_controls(step, n_steps=len(STEP_NAMES), session_key="step_idx",
                             gate_section=STEP_GATES.get(step), loading=False)
