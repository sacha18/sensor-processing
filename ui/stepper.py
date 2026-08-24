"""Back/Next controls that turn the tab bar (ui/nav.py) into a sequential
stepper, for a step that gates on a before/after (see ui.step_validate):

1. Arriving at the step, not yet reviewing: the slot shows "Next". Clicking
   it doesn't advance - it opens that before/after's fullscreen view
   (ui.fullscreen), so the button never claims to validate something the
   user hasn't actually looked at yet.
2. Reviewing (fullscreen open, not yet validated): the slot becomes
   "Validate this step" - one click both validates and advances (exiting
   fullscreen, raising `{session_key}_unlocked` - the same watermark ui.nav
   uses to keep later tabs locked), rather than needing a second "Next"
   click once the label flips back.

Steps with nothing to validate (gate_section=None) just show "Next" and
advance freely.

Every key below is scoped to `step`, not just `session_key` - each step gets
its own independent Back/Next widget identity rather than one pair reused
(with a changing label) across every step, which is what let a stale label
survive a step switch in practice.

Back and Next are each CSS-pinned independently (position: fixed, one at
bottom-left, one at bottom-right - same row, opposite corners) rather than
inline at the end of the page - they need to stay reachable without
scrolling past a long chart, including while a before/after is open in
fullscreen. No wrapper background (transparent) and the main content gets
matching bottom padding, so the floating buttons sit in their own space
instead of overlapping the last bit of chart/table content.
"""
from __future__ import annotations

import streamlit as st

from ui.fullscreen import enter_fullscreen, exit_fullscreen, is_fullscreen
from ui.step_validate import is_step_validated, mark_validated


def render_stepper_controls(step: int, n_steps: int, session_key: str, gate_section: str | None) -> None:
    unlocked_key = f"{session_key}_unlocked"
    st.session_state.setdefault(unlocked_key, 0)
    gated = gate_section is not None and not is_step_validated(gate_section)
    reviewing = gate_section is not None and is_fullscreen(gate_section)
    back_key = f"stepper_back_bar_{session_key}_{step}"
    next_key = f"stepper_next_bar_{session_key}_{step}"

    # TODO: bottom offset padded +55px above the base 1.2rem so the buttons
    # clear the Streamlit Community Cloud viewer badge pinned bottom-right -
    # revisit/remove once that badge is gone (see app.py's hide_streamlit_style).
    st.markdown(
        f"""
        <style>
        [data-testid="stMain"] {{ padding-bottom: 6rem; }}
        div[class*="st-key-stepper_back_bar_{session_key}_"], div[class*="st-key-stepper_next_bar_{session_key}_"] {{
            position: fixed !important; bottom: calc(1.2rem + 55px); z-index: 999998;
            width: fit-content !important; background: transparent !important;
            border: none !important; box-shadow: none !important; padding: 0 !important;
        }}
        div[class*="st-key-stepper_back_bar_{session_key}_"] {{ left: 1.5rem; }}
        div[class*="st-key-stepper_next_bar_{session_key}_"] {{ right: 1.5rem; }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    back_clicked = False
    if step > 0:
        with st.container(key=back_key):
            back_clicked = st.button("Back", key=f"stepper_back_{session_key}_{step}", icon=":material/arrow_back:")

    next_action = None
    if step < n_steps - 1:
        with st.container(key=next_key):
            if gated and reviewing:
                if st.button("Validate this step", key=f"stepper_next_{session_key}_{step}",
                              icon=":material/check_circle:", type="primary",
                              help="Marks the before/after above as reviewed and continues."):
                    next_action = "validate_and_advance"
            else:
                if st.button("Next", key=f"stepper_next_{session_key}_{step}", icon=":material/arrow_forward:",
                              type="primary", help="Opens the before/after so you can validate it." if gated else None):
                    next_action = "review" if gated else "advance"

    if back_clicked:
        exit_fullscreen()
        st.session_state[session_key] = step - 1
        st.rerun()
    if next_action == "review":
        enter_fullscreen(gate_section)
        st.rerun()
    elif next_action in ("validate_and_advance", "advance"):
        if next_action == "validate_and_advance":
            mark_validated(gate_section)
        exit_fullscreen()
        st.session_state[unlocked_key] = max(st.session_state[unlocked_key], step + 1)
        st.session_state[session_key] = step + 1
        st.rerun()
