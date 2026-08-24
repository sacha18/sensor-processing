"""Streamlit demo of the generic sensor cleaning/homogenization pipeline.

Run with: streamlit run app.py
Data source: $SENSOR_DATA_DIR (falls back to the bundled sample_data/ if unset
or empty) - see pipeline.resolve_data_dir(). Any folder of `<sensor_id>.json`
or `<sensor_id>.csv` observation files works, regardless of sensor count or naming.

This file is the entrypoint only - it wires the top nav, sidebar parameters,
data source and manual-override commit together, then dispatches to the
ui/generic/steps/* (or ui/tms/steps/*) module for whichever step is on
screen. The sidebar renders before the pipeline runs, so tweaking a step's
parameter there is reflected in its charts on the very same interaction -
no extra click needed. Shared
chart/theme helpers live in ui/theme.py and ui/charts.py; the pure
pandas/numpy pipeline logic lives in the pipeline/ package.
"""
from __future__ import annotations

import streamlit as st

from ui.fullscreen import any_fullscreen, inject_chrome_hide_css
from ui.generic.data_source import render_data_source
from ui.generic.nav import STEP_NAMES as GENERIC_STEP_NAMES
from ui.generic.nav import render_nav
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
from ui.mode import init_mode, render_mode_switch
from ui.stepper import render_stepper_controls
from ui.theme import inject_page_css, register_plotly_theme
from ui.tms.config import init_tms_config
from ui.tms.data_source import render_data_source_tms
from ui.tms.nav import TMS_STEP_NAMES
from ui.tms.nav import render_nav_tms
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

# Step indices, in the same order as ui.generic.nav.STEP_NAMES / ui.tms.nav.TMS_STEP_NAMES -
# named so the dispatch below reads by step, not by position.
(
    GENERIC_STEP_LOAD, GENERIC_STEP_DEDUPE, GENERIC_STEP_REGULARIZE, GENERIC_STEP_OUTLIERS,
    GENERIC_STEP_GAPFILL, GENERIC_STEP_PRODUCTION, GENERIC_STEP_ANALYSIS,
) = range(len(GENERIC_STEP_NAMES))

(
    TMS_STEP_LOAD, TMS_STEP_METADATA, TMS_STEP_INITIAL_QC, TMS_STEP_CORRECTION,
    TMS_STEP_CALIBRATION, TMS_STEP_FINAL_QC, TMS_STEP_ANALYSIS, TMS_STEP_PRODUCTION,
) = range(len(TMS_STEP_NAMES))

# step index -> the before/after section (ui.step_validate) that must be
# validated before the stepper's Next button unlocks the following step.
# A step not listed here has no before/after and advances freely.
TMS_STEP_GATES = {
    TMS_STEP_CORRECTION: "tms_correction",
    TMS_STEP_CALIBRATION: "tms_calibration",
    TMS_STEP_FINAL_QC: "tms_final_qc",
}
GENERIC_STEP_GATES = {GENERIC_STEP_GAPFILL: "gapfill"}

st.set_page_config(page_title="Sensor cleaning pipeline", layout="wide")
register_plotly_theme()
inject_page_css()
init_mode()
init_settings()
init_tms_settings()
init_tms_config()

if any_fullscreen():
    inject_chrome_hide_css()

with st.container(key="app_chrome"):
    st.title("Sensor data processor")
    mode = render_mode_switch()
    step = render_nav_tms() if mode == "tms" else render_nav()

if mode == "tms":
    render_sidebar_tms(step)
    tms_settings = get_tms_settings()
    r_tms, tms_sensors = render_data_source_tms(tms_settings, step == TMS_STEP_LOAD)

    if step == TMS_STEP_LOAD:
        tms_load.render(r_tms, tms_sensors)
    if step == TMS_STEP_METADATA:
        tms_metadata.render(r_tms)
    if step == TMS_STEP_INITIAL_QC:
        tms_initial_qc.render(r_tms, tms_sensors)
    if step == TMS_STEP_CORRECTION:
        tms_correction.render(r_tms, tms_sensors)
    if step == TMS_STEP_CALIBRATION:
        tms_calibration.render(r_tms, tms_sensors)
    if step == TMS_STEP_FINAL_QC:
        tms_final_qc.render(r_tms, tms_sensors)
    if step == TMS_STEP_ANALYSIS:
        tms_analysis.render(r_tms, tms_sensors)
    if step == TMS_STEP_PRODUCTION:
        tms_production.render(r_tms, tms_sensors)

    render_stepper_controls(step, n_steps=len(TMS_STEP_NAMES), session_key="tms_step_idx", gate_section=TMS_STEP_GATES.get(step))

else:
    render_sidebar(step)
    settings = get_settings()
    r, sensors, units = render_data_source(settings, step == GENERIC_STEP_LOAD)

    # Manual-validation overrides are applied here, unconditionally, so every step
    # (not just the Manual validation step itself) sees the committed values
    # regardless of which step is currently on screen.
    overrides_applied_count = apply_manual_overrides(r, settings.smooth_window, settings.smooth_method)

    if step == GENERIC_STEP_LOAD:
        step_load.render(r, units)
    if step == GENERIC_STEP_DEDUPE:
        step_dedupe.render(r)
    if step == GENERIC_STEP_REGULARIZE:
        step_regularize.render(r, settings.step_min, sensors)
    if step == GENERIC_STEP_OUTLIERS:
        # Detection and review live on the same screen now - no extra click
        # between spotting an outlier/gap and actually validating it.
        step_outliers.render(r, sensors, settings.use_donor_regression)
        manual_validation.render(r, sensors, overrides_applied_count)
    if step == GENERIC_STEP_GAPFILL:
        step_gapfill.render(r, sensors)
    if step == GENERIC_STEP_PRODUCTION:
        production.render(r, sensors)
    if step == GENERIC_STEP_ANALYSIS:
        analysis.render(r, sensors, settings.smooth_method, settings.smooth_window)

    render_stepper_controls(step, n_steps=len(GENERIC_STEP_NAMES), session_key="step_idx", gate_section=GENERIC_STEP_GATES.get(step))
