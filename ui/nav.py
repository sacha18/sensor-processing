"""Horizontal step tabs at the top of the main container.

Each step's own parameters now live in the sidebar (ui/sidebar.py), scoped
to whichever step is active here - which is why this isn't built on
st.tabs: st.tabs is a purely client-side toggle (all tab bodies run every
rerun, and Streamlit never tells the script which one is visible), so there
would be no way to know which step's parameters belong in the sidebar. This
nav is a row of ordinary stateful buttons instead, styled to look like a tab
bar (an underline on the active tab) so it still round-trips the selection
through session_state like any other widget.
"""
from __future__ import annotations

import streamlit as st

STEP_NAMES = [
    "Loading", "Deduplication", "Regularization", "Outliers & validation",
    "Gap filling", "Production dataset", "Analysis",
]
STEP_ICONS = [
    ":material/upload_file:", ":material/content_copy:", ":material/grid_on:",
    ":material/warning:", ":material/timeline:", ":material/dataset:", ":material/insights:",
]


def render_nav() -> int:
    """Renders the tab bar, handles clicks, and returns the active step index."""
    st.session_state.setdefault("step_idx", 0)
    current = st.session_state.step_idx
    n_steps = len(STEP_NAMES)

    css_rules = ['''
        [class*="st-key-tab_step_"] button {
            border: none !important;
            border-radius: 0 !important;
            border-bottom: 3px solid transparent !important;
            padding: 0.5rem 0.75rem !important;
        }
    ''']
    for i in range(n_steps):
        if i == current:
            css_rules.append(f'''
                .st-key-tab_step_{i} button {{
                    color: #5470c6 !important;
                    border-bottom: 3px solid #5470c6 !important;
                    font-weight: 700 !important;
                }}
            ''')
    st.markdown(f"<style>{''.join(css_rules)}</style>", unsafe_allow_html=True)

    cols = st.columns(n_steps, gap="small")
    for i, col in enumerate(cols):
        if col.button(f"{i + 1}. {STEP_NAMES[i]}", key=f"tab_step_{i}", icon=STEP_ICONS[i],
                      type="tertiary", width="stretch"):
            st.session_state.step_idx = i
            st.rerun()

    return st.session_state.step_idx
