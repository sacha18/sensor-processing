"""Data source expander: upload/sample loading, channel selection, unit labels,
and the cached pipeline run.
"""
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

import pipeline.generic as P
from ui.format import is_telemetry_channel, looks_like_tms_export
from ui.generic.settings import Settings
from ui.loading import finish_loading_gate, uploads_fingerprint
from ui.theme import CATEGORICAL_COLORS


@dataclass
class SensorMeta:
    ids: list
    label: dict   # sensor_id -> display label, e.g. "V3 (L/s)" when a unit was supplied
    color: dict   # sensor_id -> hex color


@st.cache_data(show_spinner="Running pipeline...")
def get_pipeline(raw_long, step_min, outlier_cfg, max_gap, smooth_window, smooth_method,
                  use_donor_regression, donor_min_corr):
    return P.process_pipeline(raw_long, step_min=step_min, outlier_cfg=outlier_cfg, max_interp_gap=max_gap,
                               smooth_window=smooth_window, smooth_method=smooth_method,
                               use_donor_regression=use_donor_regression, donor_min_corr=donor_min_corr)


@st.cache_data(show_spinner="Loading sensor files...")
def _load_raw_dir(data_dir):
    """Cached wrapper around P.load_raw - without this, every rerun (any
    widget interaction, not just a new upload) re-reads and re-parses every
    sensor file from disk."""
    return P.load_raw(data_dir)


@st.cache_data(show_spinner="Parsing uploaded files...")
def _load_raw_uploads(uploaded_files):
    return P.load_raw_from_uploads(uploaded_files)


_UPLOAD_KEY_BASE = "data_source_uploaded_files"
_CHANNELS_KEY_BASE = "data_source_channels"
_UNITS_KEY_BASE = "data_source_units_file"
_RELOAD_VERSION_KEY = "data_source_reload_version"
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
    needs the loading-gate priming pass (see ui.loading)."""
    uploaded_files = st.session_state.get(_versioned(_UPLOAD_KEY_BASE))
    if uploaded_files:
        return uploads_fingerprint(uploaded_files)
    return ("__sample__", st.session_state.get(_RELOAD_VERSION_KEY, 0))


def render_data_source(settings: Settings, show_ui: bool):
    """Runs the pipeline on the selected channels, returning (r, sensors, units)
    or calling st.stop() on error/empty selection. The "Data source" controls
    (file upload, channel/unit pickers) are only rendered when `show_ui` is set,
    i.e. on the Loading step - other steps just reuse the last selection via
    session_state."""
    upload_key = _versioned(_UPLOAD_KEY_BASE)
    channels_key = _versioned(_CHANNELS_KEY_BASE)
    units_key = _versioned(_UNITS_KEY_BASE)

    if show_ui:
        st.subheader("Data source", divider="gray")
        st.caption("No file? No problem - the bundled sample data loads below. Already uploaded something? "
                   "**Load sample data** switches back to it.")
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

    if uploaded_files:
        fingerprint = uploads_fingerprint(uploaded_files)
    else:
        fingerprint = ("__sample__", st.session_state.get(_RELOAD_VERSION_KEY, 0))

    if uploaded_files:
        source_label = f"{len(uploaded_files)} uploaded file(s)"
        tms_looking = [f.name for f in uploaded_files if looks_like_tms_export(f.name, f.getvalue())]
        if tms_looking:
            st.error(f"{', '.join(tms_looking)} looks like a TOMST TMS-4 raw export, not the generic pipeline's "
                     "format (phenomenon_time/result) - switch to the **TOMST TMS-4 (soil)** pipeline above to "
                     "process it.")
            st.stop()
        try:
            raw_long = _load_raw_uploads(uploaded_files)
        except Exception as e:
            st.error(f"Could not parse the uploaded files: {e}")
            st.stop()
    else:
        try:
            data_dir = P.resolve_data_dir()
        except FileNotFoundError as e:
            st.error(str(e))
            st.stop()
        source_label = str(data_dir)
        raw_long = _load_raw_dir(data_dir)

    all_channel_ids = sorted(raw_long["sensor_id"].unique())
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
    raw_long = raw_long[raw_long["sensor_id"].isin(included_channels)].reset_index(drop=True)

    units = {}
    if units_file is not None:
        try:
            units = P.parse_units_mapping(units_file.name, units_file.getvalue())
        except Exception as e:
            if show_ui:
                st.warning(f"Could not parse the unit mapping file: {e}")

    if show_ui:
        st.caption(f"Data source: **{source_label}** - each step (see sidebar) shows the data before/after that stage.")

    r = get_pipeline(raw_long, step_min=settings.step_min, outlier_cfg=settings.outlier_cfg, max_gap=settings.max_gap,
                      smooth_window=settings.smooth_window, smooth_method=settings.smooth_method,
                      use_donor_regression=settings.use_donor_regression, donor_min_corr=settings.donor_min_corr)
    finish_loading_gate(LOADING_NAMESPACE, fingerprint)
    sensor_ids = sorted(r["reg_long"]["sensor_id"].unique())
    sensors = SensorMeta(
        ids=sensor_ids,
        label={s: (f"{s} ({units[s]})" if units.get(s) else s) for s in sensor_ids},
        color={s: CATEGORICAL_COLORS[i % len(CATEGORICAL_COLORS)] for i, s in enumerate(sensor_ids)},
    )

    return r, sensors, units
