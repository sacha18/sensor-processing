"""Standalone generic-pipeline analysis page - reached via the "Analyze"
button on the Production dataset step, not part of the pipeline stepper.
"""
from __future__ import annotations

import streamlit as st

from ui.format import to_csv_bytes_cached
from ui.fullscreen import any_fullscreen, inject_chrome_hide_css
from ui.generic.data_source import render_data_source
from ui.generic.settings import get_settings, init_settings
from ui.generic.steps import analysis
from ui.stepper import fixed_bottom_right


def render_generic_analysis_page(picker_page, generic_page) -> None:
    init_settings()

    if any_fullscreen():
        inject_chrome_hide_css()

    with st.container(key="app_chrome"):
        col_back, col_title, col_change = st.columns([1, 4, 1])
        with col_back:
            if st.button("Back to pipeline", icon=":material/arrow_back:", key="analysis_back", width="stretch"):
                st.switch_page(generic_page)
        with col_title:
            st.title("Sensor data processor")
        with col_change:
            st.write("")
            if st.button("Change pipeline", icon=":material/swap_horiz:", key="change_pipeline_analysis",
                         width="stretch"):
                st.switch_page(picker_page)

    settings = get_settings()
    r, sensors, _units = render_data_source(settings, show_ui=False)
    analysis.render(r, sensors, settings.smooth_method, settings.smooth_window)

    with fixed_bottom_right("analysis_next_bar"):
        st.download_button(
            "Download", to_csv_bytes_cached(r["production"].set_index("timestamp")),
            file_name="sensors_clean_long.csv", mime="text/csv", type="primary",
            key="analysis_download", width="content",
        )
