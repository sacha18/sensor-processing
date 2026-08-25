"""Standalone TMS analysis page - reached via the "Analyze" button on the
Production dataset step, not part of the pipeline stepper. Only pulls the
finished `production` table out of the cached pipeline result - its
grouping fields (treatment, depth_cm, site, ...) are already merged in via
apply_metadata earlier in the pipeline, so a separate metadata reference
isn't needed here. The rest of that cached result (raw_wide, corrected,
calibrated, qc tables, reports, ...) is never referenced and so never has
to be carried around for this page to work.
"""
from __future__ import annotations

import streamlit as st

from ui.format import to_csv_bytes_cached
from ui.fullscreen import any_fullscreen, inject_chrome_hide_css
from ui.stepper import fixed_bottom_right
from ui.tms.config import init_tms_config
from ui.tms.data_source import has_cached_upload, render_data_source_tms
from ui.tms.settings import get_tms_settings, init_tms_settings
from ui.tms.steps import analysis as tms_analysis


def render_tms_analysis_page(picker_page, tms_page) -> None:
    init_tms_settings()
    init_tms_config()

    if any_fullscreen():
        inject_chrome_hide_css()

    with st.container(key="app_chrome"):
        col_back, col_title, col_change = st.columns([1, 4, 1])
        with col_back:
            if st.button("Back to pipeline", icon=":material/arrow_back:", key="analysis_back", width="stretch"):
                st.switch_page(tms_page)
        with col_title:
            st.title("Sensor data processor")
        with col_change:
            st.write("")
            if st.button("Change pipeline", icon=":material/swap_horiz:", key="change_pipeline_analysis",
                         width="stretch"):
                st.switch_page(picker_page)

    if not has_cached_upload():
        st.info("No data loaded yet - go to the pipeline and upload your TOMST TMS-4 export files first.")
        if st.button("Go to pipeline", icon=":material/arrow_back:"):
            st.switch_page(tms_page)
        st.stop()

    settings = get_tms_settings()
    r, sensors = render_data_source_tms(settings, show_ui=False)
    production = r["production"]
    tms_analysis.render(production, sensors)

    with fixed_bottom_right("analysis_next_bar"):
        st.download_button(
            "Download", to_csv_bytes_cached(production.set_index("timestamp")),
            file_name="tms_production.csv", mime="text/csv", type="primary",
            key="analysis_download", width="content",
        )
