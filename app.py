"""Streamlit demo of the generic sensor cleaning/homogenization pipeline.

Run with: streamlit run app.py
Data source: $SENSOR_DATA_DIR (falls back to the bundled sample_data/ if unset
or empty) - see pipeline.resolve_data_dir(). Any folder of `<sensor_id>.json`
or `<sensor_id>.csv` observation files works, regardless of sensor count or naming.

This file is the entrypoint only - it wires the top nav, sidebar parameters,
data source and manual-override commit together, then dispatches to the
ui/steps/* module for whichever step is on screen. The sidebar renders
before the pipeline runs, so tweaking a step's parameter there is reflected
in its charts on the very same interaction - no extra click needed. Shared
chart/theme helpers live in ui/theme.py and ui/charts.py; the pure
pandas/numpy pipeline logic lives in the pipeline/ package.
"""
from __future__ import annotations

import streamlit as st

from ui.data_source import render_data_source
from ui.nav import render_nav
from ui.overrides import apply_manual_overrides
from ui.settings import get_settings, init_settings
from ui.sidebar import render_sidebar
from ui.steps import (
    analysis,
    dedupe as step_dedupe,
    gapfill as step_gapfill,
    load as step_load,
    manual_validation,
    outliers as step_outliers,
    production,
    regularize as step_regularize,
)
from ui.theme import inject_page_css, register_plotly_theme

st.set_page_config(page_title="Sensor cleaning pipeline", layout="wide")
register_plotly_theme()
inject_page_css()
init_settings()

st.title("Sensor data processor")

step = render_nav()
render_sidebar(step)
settings = get_settings()
r, sensors, units = render_data_source(settings)

# Manual-validation overrides are applied here, unconditionally, so every step
# (not just the Manual validation step itself) sees the committed values
# regardless of which step is currently on screen.
overrides_applied_count = apply_manual_overrides(r, settings.smooth_window, settings.smooth_method)

if step == 0:
    step_load.render(r, units)
if step == 1:
    step_dedupe.render(r)
if step == 2:
    step_regularize.render(r, settings.step_min, sensors)
if step == 3:
    # Detection and review live on the same screen now - no extra click
    # between spotting an outlier/gap and actually validating it.
    step_outliers.render(r, sensors, settings.use_donor_regression)
    manual_validation.render(r, sensors, overrides_applied_count)
if step == 4:
    step_gapfill.render(r, sensors)
if step == 5:
    production.render(r, sensors)
if step == 6:
    analysis.render(r, sensors, settings.smooth_method, settings.smooth_window)
