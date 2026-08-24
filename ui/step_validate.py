"""Per-step "reviewed the before/after" flag.

Separate from ui.generic.steps.manual_validation's per-point outlier/gap review
(which commits actual value overrides into the production dataset) - this
just records that a human looked at a step's before/after comparison.
ui.stepper is the only thing that sets/reads it now (the pinned "Validate
this step" button at the bottom-right) - there's no separate inline button
on the step's own page anymore, that was a duplicate of the pinned one.
"""
from __future__ import annotations

import streamlit as st

_SESSION_KEY = "step_validated"


def is_step_validated(step_key: str) -> bool:
    return st.session_state.get(_SESSION_KEY, {}).get(step_key, False)


def mark_validated(step_key: str) -> None:
    st.session_state.setdefault(_SESSION_KEY, {})
    st.session_state[_SESSION_KEY][step_key] = True
