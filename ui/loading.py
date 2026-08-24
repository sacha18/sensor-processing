"""Keeps the stepper's Next/Validate button (ui.stepper) disabled for the one
extra rerun it takes to get a "loading" frame actually painted in the
browser before a heavy parse/pipeline call blocks the script.

Streamlit reruns are synchronous and blocking, and elements are streamed to
the browser in the order the script produces them. The stepper's Next button
is rendered at the very end of each page (ui.tms.page / ui.generic.page),
*after* the heavy data-source call - so simply passing `disabled=` to that
same run's Next button doesn't help: by the time that line runs, the heavy
call has already finished, and while it was running the *previous* run's
Next button (rendered seconds/minutes earlier) was still sitting on screen,
fully clickable.

The fix is a priming pass: the first time a given fingerprint shows up,
loading_pending() returns True and the page must render *just* a disabled
stepper (skipping the heavy call and step content) and call st.rerun()
itself, right after - only then does the disabled frame reach the browser
before the blocking call starts. The following pass (loading flag already
set) gets loading_pending() == False and proceeds with the real work.
"""
from __future__ import annotations

import streamlit as st


def loading_pending(namespace: str, fingerprint) -> bool:
    """Call once at the top of a page render, with a cheap-to-compute
    `fingerprint` identifying the current input (e.g. uploaded file names+
    sizes). Returns True the first time a new fingerprint shows up - the
    caller must, in that case, render a disabled stepper (nothing else heavy)
    and then call st.rerun() itself. Returns False once primed (safe to do
    the real heavy work this pass) or once already processed (nothing to do)."""
    loading_key = f"{namespace}_loading"
    seen_key = f"{namespace}_loading_fingerprint"
    if st.session_state.get(seen_key) == fingerprint:
        return False
    if not st.session_state.get(loading_key):
        st.session_state[loading_key] = True
        return True
    return False


def finish_loading_gate(namespace: str, fingerprint) -> None:
    """Call right after the heavy work for `fingerprint` actually completes."""
    st.session_state[f"{namespace}_loading_fingerprint"] = fingerprint
    st.session_state[f"{namespace}_loading"] = False


def uploads_fingerprint(uploaded_files) -> tuple:
    """Cheap (metadata-only, no content read) identity for a file_uploader's
    current selection - stable across reruns that don't actually change it."""
    if not uploaded_files:
        return ("__none__",)
    return tuple((f.name, f.size) for f in uploaded_files)
