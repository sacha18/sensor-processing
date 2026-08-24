"""Streamlit entrypoint - wires the three top-level pages (pipeline picker,
generic pipeline, TOMST TMS-4 pipeline) via st.navigation, each with its own
URL ("", "generic", "tms"). Session state is shared across pages (same
Streamlit session) but each pipeline's keys are namespaced (ui.generic.settings
vs ui.tms.settings, ...), so picking a pipeline on the landing page is a
one-way lock for the rest of the session: the other pipeline's data source
and cached pipeline result are simply never initialized, no runtime
toggle/teardown to maintain.

Run with: streamlit run app.py
Data source: $SENSOR_DATA_DIR (falls back to the bundled sample_data/ if unset
or empty) - see pipeline.resolve_data_dir(). Any folder of `<sensor_id>.json`
or `<sensor_id>.csv` observation files works, regardless of sensor count or naming.
"""
from __future__ import annotations

import logging

import streamlit as st

from ui.generic.page import render_generic_page
from ui.picker import render_picker
from ui.theme import inject_page_css, register_plotly_theme
from ui.tms.page import render_tms_page

# Without this, modules' logger.info(...) calls are silently dropped -
# Python's default has no handler below WARNING.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

st.set_page_config(page_title="Sensor cleaning pipeline", layout="wide")
register_plotly_theme()
inject_page_css()

generic_page = st.Page(lambda: render_generic_page(picker_page), title="Generic pipeline",
                        icon=":material/show_chart:", url_path="generic")
tms_page = st.Page(lambda: render_tms_page(picker_page), title="TOMST TMS-4 (soil)",
                    icon=":material/grass:", url_path="tms")
picker_page = st.Page(lambda: render_picker(generic_page, tms_page), title="Choose pipeline",
                       url_path="", default=True)

st.navigation([picker_page, generic_page, tms_page], position="hidden").run()
