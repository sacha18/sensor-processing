"""TMS "Data source" controls: upload/sample loading of TOMST TMS-4 export
files and the cached pipeline run - mirrors ui/generic/data_source.py's shape,
but for the wide multi-channel TMS format and its own config tables (metadata/
correction/calibration/field events, see ui/tms/config.py) instead of a
units-label file.
"""
from __future__ import annotations

import logging

import streamlit as st

import pipeline.tms as TMS
from ui.format import looks_like_generic_export
from ui.generic.data_source import SensorMeta
from ui.loading import finish_loading_gate, uploads_fingerprint
from ui.theme import CATEGORICAL_COLORS
from ui.tms.config import get_table
from ui.tms.settings import TmsSettings

logger = logging.getLogger(__name__)

_UPLOAD_KEY_BASE = "tms_uploaded_files"
_RELOAD_VERSION_KEY = "tms_reload_version"
LOADING_NAMESPACE = "tms_data_source"


def _versioned(key_base: str) -> str:
    """Appends the current "reload" version to a widget key - bumped by the
    "Load sample data" button below. A plain st.session_state.pop() of the
    file_uploader's key clears its *value* but Streamlit's file_uploader
    component keeps showing the previously attached file client-side unless
    the widget itself gets a new key (same trick as ui.tms.config.editor_key)."""
    return f"{key_base}_{st.session_state.get(_RELOAD_VERSION_KEY, 0)}"


def peek_tms_fingerprint() -> tuple:
    """The fingerprint render_data_source_tms will use this run, without
    rendering anything - Streamlit resolves a widget's current value into
    session_state before the script body runs, so this is accurate even
    before st.file_uploader(key=upload_key) is (re-)called this pass. Lets
    ui.tms.page decide, before doing any rendering, whether this run needs
    the loading-gate priming pass (see ui.loading)."""
    uploaded_files = st.session_state.get(_versioned(_UPLOAD_KEY_BASE))
    if uploaded_files:
        return uploads_fingerprint(uploaded_files)
    return ("__sample__", st.session_state.get(_RELOAD_VERSION_KEY, 0))


@st.cache_data(show_spinner="Running TMS pipeline...")
def get_tms_pipeline(raw_wide, metadata_df, correction_params, calibration_params,
                      field_events, qc_cfg, final_qc_cfg, step_min):
    return TMS.process_tms_pipeline(raw_wide, metadata_df, correction_params, calibration_params,
                                     field_events=field_events, qc_cfg=qc_cfg,
                                     final_qc_cfg=final_qc_cfg, step_min=step_min)


@st.cache_data(show_spinner="Loading TOMST export files...")
def _load_tms_raw_dir(data_dir):
    """Cached wrapper around TMS.load_tms_raw - without this, every rerun
    (any widget interaction, not just a new upload) re-reads and re-parses
    every TOMST export file from disk."""
    return TMS.load_tms_raw(data_dir)


@st.cache_data(show_spinner="Parsing uploaded files...")
def _load_tms_raw_uploads(uploaded_files):
    return TMS.load_tms_raw_from_uploads(uploaded_files)


def render_data_source_tms(settings: TmsSettings, show_ui: bool, skip_heavy: bool = False):
    """Runs the TMS pipeline, returning (r, sensors) or calling st.stop() on
    error/empty selection. Upload controls only render when `show_ui` is set,
    i.e. on the "Loading & continuity" step - other steps reuse the last
    upload via session_state, same pattern as ui/data_source.py.

    `skip_heavy` still renders the upload controls (if show_ui) but returns
    (None, None) immediately, skipping the parse/pipeline work - used by the
    loading-gate priming pass (ui.loading). A widget not re-declared on a
    run gets unmounted client-side, and file_uploader loses track of
    already-attached files when that happens."""
    upload_key = _versioned(_UPLOAD_KEY_BASE)

    if show_ui:
        st.subheader("Data source", divider="gray")
        col_upload, col_sample = st.columns([5, 1])
        with col_upload:
            uploaded_files = st.file_uploader(
                "Drop your TOMST TMS-4 export files here (one or more per sensor)",
                type=["csv", "zip"], accept_multiple_files=True, key=upload_key,
                help="Standard TOMST export naming: data_<sensor serial>_<yyyy>_<mm>_<dd>_<part>.csv. Multiple "
                     "downloads of the same physical sensor are grouped and merged automatically. For a large "
                     "session (hundreds of files), zip them up and drop the single **.zip** instead - one upload "
                     "is far more reliable than one browser request per file. A previously downloaded "
                     "**tms_merged_raw_archive.csv** is also accepted - drop it in alone to resume a session, or "
                     "alongside new raw files to add only what's new.",
            )
        with col_sample:
            st.write("")  # vertical spacer to align the button with the uploader, not its label
            st.write("")
            if st.button("Load sample data", icon=":material/restart_alt:", width="stretch",
                         help="Discards any uploaded files, switching back to the bundled TOMST sample sensors."):
                st.session_state[_RELOAD_VERSION_KEY] = st.session_state.get(_RELOAD_VERSION_KEY, 0) + 1
                st.rerun()
    else:
        uploaded_files = st.session_state.get(upload_key)

    if uploaded_files:
        fingerprint = uploads_fingerprint(uploaded_files)
    else:
        fingerprint = ("__sample__", st.session_state.get(_RELOAD_VERSION_KEY, 0))

    if skip_heavy:
        return None, None

    if uploaded_files:
        logger.info("TMS data source: %d file(s) received from the browser", len(uploaded_files))
        generic_looking = [f.name for f in uploaded_files if looks_like_generic_export(f.name, f.getvalue())]
        if generic_looking:
            st.error(f"{', '.join(generic_looking)} looks like the generic pipeline's format (phenomenon_time/"
                     "result), not a TOMST TMS-4 raw export - switch to the **Generic pipeline** above to process it.")
            st.stop()
        try:
            raw_wide, failed = _load_tms_raw_uploads(uploaded_files)
        except Exception as e:
            st.error(f"Could not parse the uploaded files: {e}")
            st.stop()
        if failed:
            st.warning(
                f"{len(failed)} of {len(uploaded_files)} uploaded file(s) could not be parsed and were skipped "
                "(possibly lost/corrupted in transit - try re-uploading just these):\n\n"
                + "\n".join(f"- **{name}**: {err}" for name, err in failed)
            )
    else:
        try:
            data_dir = TMS.resolve_tms_data_dir()
        except FileNotFoundError as e:
            st.error(str(e))
            st.stop()
        raw_wide = _load_tms_raw_dir(data_dir)

    r = get_tms_pipeline(
        raw_wide, get_table("metadata"), get_table("correction"), get_table("calibration"),
        get_table("field_events"), settings.qc_cfg, settings.final_qc_cfg, settings.step_min,
    )
    finish_loading_gate(LOADING_NAMESPACE, fingerprint)
    sensor_ids = sorted(raw_wide["sensor_id"].unique())
    sensors = SensorMeta(
        ids=sensor_ids, label={s: s for s in sensor_ids},
        color={s: CATEGORICAL_COLORS[i % len(CATEGORICAL_COLORS)] for i, s in enumerate(sensor_ids)},
    )
    return r, sensors
