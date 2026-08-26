"""Data source expander: upload/sample loading, channel selection, unit labels,
and the (disk-cached, per-stage) pipeline run.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import streamlit as st

import pipeline.generic as P
from pipeline import store
from ui.format import is_telemetry_channel, looks_like_tms_export
from ui.generic.settings import Settings
from ui.loading import finish_loading_gate, live_uploads, uploads_fingerprint
from ui.session import get_session_id
from ui.theme import CATEGORICAL_COLORS


@dataclass
class SensorMeta:
    ids: list
    label: dict   # sensor_id -> display label, e.g. "V3 (L/s)" when a unit was supplied
    color: dict   # sensor_id -> hex color


def _fingerprint_hash(fingerprint) -> str:
    return hashlib.sha1(repr(fingerprint).encode()).hexdigest()[:16]


_LAZY_LOADERS = {
    "span": lambda p: store.read_df(p).set_index("sensor_id"),
    "grid": lambda p: store.read_df(p)["timestamp"],
    "sim": store.load_pickle,
}


def _materialize(paths: dict) -> dict:
    """Wraps a process_pipeline() result ({stage_name: Path}) in a dict-like
    object that reads a stage into a DataFrame (or unpickles it, for "sim")
    only the first time a step actually accesses it - a single step only
    ever touches a handful of the pipeline's 12 stage outputs, so this is
    the difference between holding 1-3 full DataFrames in memory per render
    vs. all 12 regardless of which step is on screen."""
    return store.LazyFrameDict(paths, _LAZY_LOADERS)


_UPLOAD_KEY_BASE = "data_source_uploaded_files"
_CHANNELS_KEY_BASE = "data_source_channels"
_UNITS_KEY_BASE = "data_source_units_file"
_RELOAD_VERSION_KEY = "data_source_reload_version"
_RAW_CACHE_FP_KEY_BASE = "data_source_raw_long_cache_fp"
LOADING_NAMESPACE = "generic_data_source"


def _versioned(key_base: str) -> str:
    """Appends the current "reload" version to a widget key - bumped by the
    "Load sample data" button below. A plain st.session_state.pop() of e.g.
    the file_uploader's key clears its *value* but Streamlit's file_uploader
    component keeps showing the previously attached file client-side unless
    the widget itself gets a new key (same trick as ui.tms.config.editor_key)."""
    return f"{key_base}_{st.session_state.get(_RELOAD_VERSION_KEY, 0)}"


def peek_generic_fingerprint() -> tuple:
    """The fingerprint render_data_source will use this run, without
    rendering anything - Streamlit resolves a widget's current value into
    session_state before the script body runs, so this is accurate even
    before st.file_uploader(key=upload_key) is (re-)called this pass. Lets
    ui.generic.page decide, before doing any rendering, whether this run
    needs the loading-gate priming pass (see ui.loading).

    Falls back to the last-cached-upload fingerprint (not straight to
    "__sample__") when the file_uploader's own session_state value is
    empty - Streamlit doesn't reliably keep a file_uploader's attached
    files across many reruns where it isn't the widget being interacted
    with (e.g. on the standalone analysis page, or uploading something in
    a *different* file_uploader elsewhere in the app), so this is the
    difference between "no file uploaded" and "already uploaded and parsed
    earlier this session"."""
    uploaded_files = st.session_state.get(_versioned(_UPLOAD_KEY_BASE))
    if uploaded_files:
        return uploads_fingerprint(uploaded_files)
    cached_fp = st.session_state.get(_versioned(_RAW_CACHE_FP_KEY_BASE))
    if cached_fp is not None:
        return cached_fp
    return ("__sample__", st.session_state.get(_RELOAD_VERSION_KEY, 0))


def render_data_source(settings: Settings, show_ui: bool, skip_heavy: bool = False):
    """Runs the pipeline on the selected channels, returning (r, sensors, units)
    or calling st.stop() on error/empty selection. The "Data source" controls
    (file upload, channel/unit pickers) are only rendered when `show_ui` is set,
    i.e. on the Loading step - other steps just reuse the last selection via
    session_state.

    `skip_heavy` still renders the main file_uploader (if show_ui) but
    returns (None, None, None) immediately, skipping the parse/pipeline
    work - used by the loading-gate priming pass (ui.loading). A widget not
    re-declared on a run gets unmounted client-side, and file_uploader
    loses track of already-attached files when that happens."""
    upload_key = _versioned(_UPLOAD_KEY_BASE)
    channels_key = _versioned(_CHANNELS_KEY_BASE)
    units_key = _versioned(_UNITS_KEY_BASE)
    raw_cache_fp_key = _versioned(_RAW_CACHE_FP_KEY_BASE)

    if show_ui:
        st.subheader("Data source", divider="gray")
        col_upload, col_sample = st.columns([5, 1])
        with col_upload:
            uploaded_files = st.file_uploader(
                "Drop your sensor files here (one file per sensor)",
                type=["json", "csv"], accept_multiple_files=True, key=upload_key,
                help="JSON or CSV, same columns either way: phenomenon_time, result (observation_id optional). "
                     "The filename (without extension) becomes that sensor's id.",
            )
        with col_sample:
            st.write("")  # vertical spacer to align the button with the uploader, not its label
            st.write("")
            if st.button("Load sample data", icon=":material/restart_alt:", width="stretch",
                         help="Discards any uploaded files and channel selection, switching back to the bundled "
                              "sample dataset."):
                st.session_state[_RELOAD_VERSION_KEY] = st.session_state.get(_RELOAD_VERSION_KEY, 0) + 1
                st.rerun()
    else:
        uploaded_files = st.session_state.get(upload_key)
    uploaded_files = live_uploads(uploaded_files)

    if uploaded_files:
        fingerprint = uploads_fingerprint(uploaded_files)
    else:
        fingerprint = st.session_state.get(raw_cache_fp_key) or \
            ("__sample__", st.session_state.get(_RELOAD_VERSION_KEY, 0))

    if skip_heavy:
        return None, None, None

    pipeline_dir = store.session_dir(get_session_id(), "generic")
    raw_dir = pipeline_dir / "raw" / _fingerprint_hash(fingerprint)

    if uploaded_files:
        tms_looking = [f.name for f in uploaded_files if looks_like_tms_export(f.name, f.getvalue())]
        if tms_looking:
            st.error(f"{', '.join(tms_looking)} looks like a TOMST TMS-4 raw export, not the generic pipeline's "
                     "format (phenomenon_time/result) - switch to the **TOMST TMS-4 (soil)** pipeline above to "
                     "process it.")
            st.stop()
        if not raw_dir.exists():
            try:
                P.write_raw_uploads_to_store(uploaded_files, raw_dir)
            except Exception as e:
                st.error(f"Could not parse the uploaded files: {e}")
                st.stop()
        # Fingerprint (not the parsed data itself) is stashed independently of
        # the widget: Streamlit doesn't reliably keep a file_uploader's
        # attached files across many reruns spent on other steps/pages (see
        # peek_generic_fingerprint) - the parsed data lives on disk under
        # raw_dir, keyed by this same fingerprint, so remembering just the
        # fingerprint is enough to find it again on a later rerun.
        st.session_state[raw_cache_fp_key] = fingerprint
    elif raw_dir.exists():
        pass  # already parsed earlier this session (or a prior container run) - reuse on disk
    else:
        try:
            data_dir = P.resolve_data_dir()
        except FileNotFoundError as e:
            st.error(str(e))
            st.stop()
        P.write_raw_dir_to_store(raw_dir, data_dir)

    raw_paths = sorted(raw_dir.glob("*.parquet"))
    all_channel_ids = sorted(P.sensor_id_of_part(p) for p in raw_paths)
    default_channels = [s for s in all_channel_ids if not is_telemetry_channel(s)]

    if show_ui:
        col_ch, col_units = st.columns([3, 2])
        with col_ch:
            included_channels = st.multiselect(
                "Channels to include", all_channel_ids, default=default_channels, key=channels_key,
                help="Device telemetry (battery, radio signal, enclosure temp/humidity, firmware version, ...) is "
                     "excluded by default - only real measurement channels feed the pipeline. Adjust if needed.",
            )
        with col_units:
            units_file = st.file_uploader(
                "Optional: unit labels per sensor", type=["json", "csv"], key=units_key,
                help="Different sensors rarely measure the same thing (a piezometer in cm, a flow gauge in L/s, "
                     "a scintillometer in W/m2, ...) - drop a small mapping file to label charts accordingly. "
                     "Display only, doesn't affect any computation. CSV with sensor_id,unit columns, or JSON "
                     "{\"sensor_id\": \"unit\"}.",
            )
    else:
        included_channels = st.session_state.get(channels_key, default_channels)
        units_file = st.session_state.get(units_key)

    if not included_channels:
        st.error("No channels selected - pick at least one to run the pipeline.")
        st.stop()
    included = set(included_channels)
    raw_paths = [p for p in raw_paths if P.sensor_id_of_part(p) in included]

    units = {}
    if units_file is not None:
        try:
            units = P.parse_units_mapping(units_file.name, units_file.getvalue())
        except Exception as e:
            if show_ui:
                st.warning(f"Could not parse the unit mapping file: {e}")

    with st.status("Running pipeline...", expanded=False) as status:
        def _progress(label: str) -> None:
            status.update(label=label, expanded=True)
            st.write(f"- {label}...")

        paths = P.process_pipeline(pipeline_dir, raw_paths, step_min=settings.step_min, outlier_cfg=settings.outlier_cfg,
                                    max_interp_gap=settings.max_gap, smooth_window=settings.smooth_window,
                                    smooth_method=settings.smooth_method, use_donor_regression=settings.use_donor_regression,
                                    donor_min_corr=settings.donor_min_corr, progress=_progress)
        status.update(label="Pipeline up to date", state="complete", expanded=False)
    r = _materialize(paths)
    finish_loading_gate(LOADING_NAMESPACE, fingerprint)
    sensor_ids = sorted(r["reg_long"]["sensor_id"].unique())
    sensors = SensorMeta(
        ids=sensor_ids,
        label={s: (f"{s} ({units[s]})" if units.get(s) else s) for s in sensor_ids},
        color={s: CATEGORICAL_COLORS[i % len(CATEGORICAL_COLORS)] for i, s in enumerate(sensor_ids)},
    )

    return r, sensors, units
