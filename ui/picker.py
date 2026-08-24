"""Landing page: pick which pipeline to work with for this session.

Each pipeline's session_state is namespaced independently (ui.generic.settings
vs ui.tms.settings, ui.generic.data_source vs ui.tms.data_source, ...), so
picking one here never touches the other's - unlike a same-page runtime
toggle, there's no shared state to tear down or guard with a confirmation
dialog. A page you never visit in a session never gets initialized at all.
"""
from __future__ import annotations

import streamlit as st


def render_picker(generic_page, tms_page) -> None:
    st.title("Sensor data processor")
    st.caption("Choose which pipeline to work with for this session.")

    # Columns stretch to equal height and each card's vertical block becomes a
    # flex column so the "Open" button sits flush at the bottom regardless of
    # how much description text the card above it has - keeps both cards the
    # same height and their buttons aligned, on wide screens and stacked mobile alike.
    st.markdown("""
    <style>
    div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-picker-card-"]) {
        align-items: stretch;
    }
    div[data-testid="stColumn"]:has(div[class*="st-key-picker-card-"]) {
        display: flex;
    }
    /* Streamlit wraps each container in its own stLayoutWrapper, which does not
       stretch to fill the column on its own - it has to be told to grow too,
       otherwise the card below it (and its "height: 100%") has nothing to fill. */
    div[data-testid="stLayoutWrapper"]:has(> div[class*="st-key-picker-card-"]) {
        flex: 1;
    }
    div[class*="st-key-picker-card-"] {
        height: 100%;
    }
    div[class*="st-key-picker-card-"] div[data-testid="stButton"] {
        margin-top: auto;
        padding-top: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

    col_generic, col_tms = st.columns(2)
    with col_generic, st.container(border=True, key="picker-card-generic"):
        st.subheader(":material/show_chart: Generic pipeline")
        st.write("Single-value sensors - dedup, regularization, "
                 "outlier detection, gap filling, and a production dataset.")
        if st.button("Open", key="pick_generic", type="primary", width="stretch"):
            st.switch_page(generic_page)
    with col_tms, st.container(border=True, key="picker-card-tms"):
        st.subheader(":material/grass: TOMST TMS-4 (soil)")
        st.write("TOMST TMS-4 soil sensor exports (T1/T2/T3/Signal) - metadata, signal correction, "
                 "VWC calibration, and cross-channel QC.")
        if st.button("Open", key="pick_tms", type="primary", width="stretch"):
            st.switch_page(tms_page)