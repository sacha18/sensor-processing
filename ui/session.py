"""Per-browser-session identity for the on-disk DuckDB/Parquet store (see
pipeline.store) - one id per Streamlit session, generated once and reused
across reruns so a session's staged pipeline results live in their own
directory and persist across reruns/app restarts, instead of Streamlit's
in-memory (and per-process, not per-browser-tab) cache_data.
"""
from __future__ import annotations

import streamlit as st

from pipeline import store

_SESSION_ID_KEY = "_store_session_id"


def get_session_id() -> str:
    if _SESSION_ID_KEY not in st.session_state:
        st.session_state[_SESSION_ID_KEY] = store.new_session_id()
    return st.session_state[_SESSION_ID_KEY]
