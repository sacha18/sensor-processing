"""TMS "Data source" controls: upload of TOMST TMS-4 export files and the
(disk-cached, per-stage) pipeline run - mirrors ui/generic/data_source.py's
shape, but for the wide multi-channel TMS format and its own config tables
(metadata/correction/calibration/field events, see ui/tms/config.py) instead
of a units-label file. No bundled sample dataset - a real upload is required.
"""
from __future__ import annotations

import hashlib
import logging

import streamlit as st

import pipeline.tms as TMS
from pipeline import store
from ui.format import looks_like_generic_export
from ui.generic.data_source import SensorMeta
from ui.loading import finish_loading_gate, live_uploads, uploads_fingerprint
from ui.session import get_session_id
from ui.theme import CATEGORICAL_COLORS
from ui.tms.config import get_table
from ui.tms.settings import TmsSettings

logger = logging.getLogger(__name__)

_UPLOAD_KEY = "tms_uploaded_files"
_RAW_CACHE_FP_KEY = "tms_raw_wide_cache_fp"
_NO_UPLOAD_FINGERPRINT = ("__none__",)
LOADING_NAMESPACE = "tms_data_source"


def _fingerprint_hash(fingerprint) -> str:
    return hashlib.sha1(repr(fingerprint).encode()).hexdigest()[:16]


def _materialize(paths: dict) -> dict:
    """Wraps a process_tms_pipeline() result ({stage_name: Path}) in a
    dict-like object that reads a stage into a DataFrame only the first time
    a step actually accesses it - a single step only ever touches a handful
    of the pipeline's 11 stage outputs (raw_wide/merged/with_metadata/qc/
    corrected/calibrated/final/production/reports), so this is the
    difference between holding 1-3 full DataFrames in memory per render vs.
    all 11 regardless of which step is on screen. On a real multi-hundred-
    file upload, each stage can be millions of rows - materializing every
    one of them on every rerun is exactly the kind of memory spike that
    gets a container OOM-killed."""
    return store.LazyFrameDict(paths)


def has_cached_upload() -> bool:
    """Whether a TMS upload has already been parsed this session - lets a
    page reached outside the normal step flow (e.g. the standalone
    analysis page) show a targeted "go upload first" message instead of
    render_data_source_tms's own st.stop(), which assumes its file_uploader
    widget is visible on the current page."""
    return _RAW_CACHE_FP_KEY in st.session_state


def peek_tms_fingerprint() -> tuple:
    """The fingerprint render_data_source_tms will use this run, without
    rendering anything - Streamlit resolves a widget's current value into
    session_state before the script body runs, so this is accurate even
    before st.file_uploader(key=_UPLOAD_KEY) is (re-)called this pass. Lets
    ui.tms.page decide, before doing any rendering, whether this run needs
    the loading-gate priming pass (see ui.loading).

    Falls back to the last-cached-upload fingerprint (not straight to "no
    upload") when the file_uploader's own session_state value is empty -
    Streamlit doesn't reliably keep a file_uploader's attached files across
    many reruns where it isn't the widget being interacted with (e.g.
    uploading something in a *different* file_uploader elsewhere in the
    app), so this is the difference between "no file uploaded" and "already
    uploaded and parsed earlier this session"."""
    uploaded_files = st.session_state.get(_UPLOAD_KEY)
    if uploaded_files:
        return uploads_fingerprint(uploaded_files)
    return st.session_state.get(_RAW_CACHE_FP_KEY) or _NO_UPLOAD_FINGERPRINT


def render_data_source_tms(settings: TmsSettings, show_ui: bool, skip_heavy: bool = False):
    """Runs the TMS pipeline, returning (r, sensors) or calling st.stop() on
    error/empty selection/no upload. Upload controls only render when
    `show_ui` is set, i.e. on the "Loading & continuity" step - other steps
    reuse the last upload via session_state, same pattern as ui/data_source.py.

    `skip_heavy` still renders the upload controls (if show_ui) but returns
    (None, None) immediately, skipping the parse/pipeline work - used by the
    loading-gate priming pass (ui.loading). A widget not re-declared on a
    run gets unmounted client-side, and file_uploader loses track of
    already-attached files when that happens."""
    if show_ui:
        st.subheader("Data source", divider="gray")
        uploaded_files = st.file_uploader(
            "Drop your TOMST TMS-4 export files here (one or more per sensor)",
            type=["csv", "zip"], accept_multiple_files=True, key=_UPLOAD_KEY,
            help="Standard TOMST export naming: data_<sensor serial>_<yyyy>_<mm>_<dd>_<part>.csv. Multiple "
                 "downloads of the same physical sensor are grouped and merged automatically. For a large "
                 "session (hundreds of files), zip them up and drop the single **.zip** instead - one upload "
                 "is far more reliable than one browser request per file. A previously downloaded "
                 "**tms_merged_raw_archive.csv** is also accepted - drop it in alone to resume a session, or "
                 "alongside new raw files to add only what's new.",
        )
    else:
        uploaded_files = st.session_state.get(_UPLOAD_KEY)
    uploaded_files = live_uploads(uploaded_files)

    if uploaded_files:
        fingerprint = uploads_fingerprint(uploaded_files)
    else:
        fingerprint = st.session_state.get(_RAW_CACHE_FP_KEY) or _NO_UPLOAD_FINGERPRINT

    if skip_heavy:
        return None, None

    pipeline_dir = store.session_dir(get_session_id(), "tms")
    raw_dir = pipeline_dir / "raw" / _fingerprint_hash(fingerprint)

    if uploaded_files:
        logger.info("TMS data source: %d file(s) received from the browser", len(uploaded_files))
        generic_looking = [f.name for f in uploaded_files if looks_like_generic_export(f.name, f.getvalue())]
        if generic_looking:
            st.error(f"{', '.join(generic_looking)} looks like the generic pipeline's format (phenomenon_time/"
                     "result), not a TOMST TMS-4 raw export - switch to the **Generic pipeline** above to process it.")
            st.stop()
        failed = []
        if not raw_dir.exists():
            try:
                _, failed = TMS.write_tms_raw_uploads_to_store(uploaded_files, raw_dir)
            except Exception as e:
                st.error(f"Could not parse the uploaded files: {e}")
                st.stop()
        if failed:
            st.warning(
                f"{len(failed)} of {len(uploaded_files)} uploaded file(s) could not be parsed and were skipped "
                "(possibly lost/corrupted in transit - try re-uploading just these):\n\n"
                + "\n".join(f"- **{name}**: {err}" for name, err in failed)
            )
        # Fingerprint (not the parsed data itself) is stashed independently of
        # the widget: Streamlit doesn't reliably keep a file_uploader's
        # attached files across many reruns spent on other steps/widgets (see
        # peek_tms_fingerprint) - the parsed data lives on disk under raw_dir,
        # keyed by this same fingerprint, so remembering just the fingerprint
        # is enough to find it again on a later rerun.
        st.session_state[_RAW_CACHE_FP_KEY] = fingerprint
    elif raw_dir.exists():
        pass  # already parsed earlier this session (or a prior container run) - reuse on disk
    else:
        st.info("Upload your TOMST TMS-4 export files above to get started.")
        st.stop()

    raw_paths = sorted(raw_dir.glob("*.parquet"))
    with st.status("Running TMS pipeline...", expanded=False) as status:
        def _progress(label: str) -> None:
            status.update(label=label, expanded=True)
            st.write(f"- {label}...")

        paths = TMS.process_tms_pipeline(
            pipeline_dir, raw_paths, get_table("metadata"), get_table("correction"), get_table("calibration"),
            get_table("field_events"), settings.qc_cfg, settings.final_qc_cfg, settings.step_min,
            progress=_progress,
        )
        status.update(label="Pipeline up to date", state="complete", expanded=False)
    r = _materialize(paths)
    finish_loading_gate(LOADING_NAMESPACE, fingerprint)
    sensor_ids = sorted(r["merged"]["sensor_id"].unique())
    sensors = SensorMeta(
        ids=sensor_ids, label={s: s for s in sensor_ids},
        color={s: CATEGORICAL_COLORS[i % len(CATEGORICAL_COLORS)] for i, s in enumerate(sensor_ids)},
    )
    return r, sensors
