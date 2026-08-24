"""Horizontal step tabs at the top of the main container - a stepper, not
free-form tabs: a tab beyond the furthest step reached is locked (disabled,
shown with a lock icon) until ui.stepper's Next button unlocks it, which it
only does once any before/after gating the current step is validated. That
"furthest reached" watermark lives in `{session_key}_unlocked`.

Each step's own parameters now live in the sidebar (ui/generic/sidebar.py), scoped
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


def render_nav(step_names: list = STEP_NAMES, step_icons: list = STEP_ICONS, session_key: str = "step_idx") -> int:
    """Renders the tab bar, handles clicks, and returns the active step index.
    step_names/step_icons/session_key let a second, independent nav (e.g. the
    TMS workflow's ui/tms/nav.py) reuse this same tab-bar look without sharing
    step state with the generic pipeline's nav."""
    st.session_state.setdefault(session_key, 0)
    unlocked_key = f"{session_key}_unlocked"
    st.session_state.setdefault(unlocked_key, 0)
    current = st.session_state[session_key]
    max_unlocked = st.session_state[unlocked_key]
    n_steps = len(step_names)
    key_prefix = f"tab_{session_key}_"

    css_rules = [f'''
        [class*="st-key-{key_prefix}"] button {{
            border: none !important;
            border-radius: 0 !important;
            border-bottom: 3px solid transparent !important;
            padding: 0.5rem 0.4rem !important;
            white-space: normal !important;
            line-height: 1.2 !important;
            font-size: clamp(0.65rem, 1.3vw, 1rem) !important;
        }}
        [class*="st-key-{key_prefix}"] button p {{
            font-size: inherit !important;
            line-height: inherit !important;
        }}
    ''']
    for i in range(n_steps):
        if i == current:
            css_rules.append(f'''
                .st-key-{key_prefix}{i} button {{
                    color: #5470c6 !important;
                    border-bottom: 3px solid #5470c6 !important;
                    font-weight: 700 !important;
                }}
            ''')
    st.markdown(f"<style>{''.join(css_rules)}</style>", unsafe_allow_html=True)

    cols = st.columns(n_steps, gap="small")
    for i, col in enumerate(cols):
        locked = i > max_unlocked
        icon = ":material/lock:" if locked else step_icons[i]
        if col.button(step_names[i], key=f"{key_prefix}{i}", icon=icon,
                      type="tertiary", width="stretch", disabled=locked):
            st.session_state[session_key] = i
            st.rerun()

    return st.session_state[session_key]
