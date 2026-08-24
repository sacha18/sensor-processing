"""Fullscreen mode for a before/after chart - hides everything else: the
shared page chrome (title/pipeline switch/step nav/sidebar - rendered once
in app.py, outside any step) via CSS, and each step's own non-chart content
(params editor, uploads, tables, ...) by just not building it in Python when
its section is active - see is_fullscreen() usage in ui/tms/steps/* and
ui/generic/steps/gapfill.py. Only one section can be fullscreen at a time.

Entirely driven by ui.stepper (Next opens it on a step that needs
validating, Next-turned-"Validate this step" closes it once validated) -
there's no standalone toggle button.
"""
from __future__ import annotations

import streamlit as st

_SESSION_KEY = "fullscreen_section"

_CHROME_HIDE_CSS = """
<style>
[data-testid="stSidebar"] { display: none !important; }
.st-key-app_chrome { display: none !important; }
</style>
"""


def is_fullscreen(section_key: str) -> bool:
    return st.session_state.get(_SESSION_KEY) == section_key


def any_fullscreen() -> bool:
    return st.session_state.get(_SESSION_KEY) is not None


def enter_fullscreen(section_key: str) -> None:
    """Jumps straight into `section_key`'s fullscreen before/after - used by
    ui.stepper so clicking Next on a step that still needs validating drops
    the user right into the review instead of just refusing to advance."""
    st.session_state[_SESSION_KEY] = section_key


def exit_fullscreen() -> None:
    """Used by ui.stepper before actually changing step - leaving a section's
    fullscreen state on while navigating to a different step would keep the
    page chrome hidden with no way back if that step has no fullscreen
    toggle of its own."""
    st.session_state[_SESSION_KEY] = None


def inject_chrome_hide_css() -> None:
    """Called once from app.py, only when any_fullscreen() - hides the page
    chrome that lives outside every step's own render() function."""
    st.markdown(_CHROME_HIDE_CSS, unsafe_allow_html=True)
