"""TMS "Data source" controls: upload/sample loading of TOMST TMS-4 export
files and the cached pipeline run - mirrors ui/generic/data_source.py's shape,
but for the wide multi-channel TMS format and its own config tables (metadata/
correction/calibration/field events, see ui/tms/config.py) instead of a
units-label file.
"""
from __future__ import annotations

import streamlit as st

import pipeline.tms as TMS
from ui.format import looks_like_generic_export
from ui.generic.data_source import SensorMeta
from ui.theme import CATEGORICAL_COLORS
from ui.tms.config import get_table
from ui.tms.settings import TmsSettings

_UPLOAD_KEY = "tms_uploaded_files"


@st.cache_data(show_spinner="Running TMS pipeline...")
def get_tms_pipeline(raw_wide, metadata_df, correction_params, calibration_params,
                      field_events, qc_cfg, final_qc_cfg, step_min):
    return TMS.process_tms_pipeline(raw_wide, metadata_df, correction_params, calibration_params,
                                     field_events=field_events, qc_cfg=qc_cfg,
                                     final_qc_cfg=final_qc_cfg, step_min=step_min)


def render_data_source_tms(settings: TmsSettings, show_ui: bool):
    """Runs the TMS pipeline, returning (r, sensors) or calling st.stop() on
    error/empty selection. Upload controls only render when `show_ui` is set,
    i.e. on the "Loading & continuity" step - other steps reuse the last
    upload via session_state, same pattern as ui/data_source.py."""
    if show_ui:
        st.subheader("Data source", divider="gray")
        st.caption("No file? No problem - the bundled TOMST sample sensors load automatically below.")
        uploaded_files = st.file_uploader(
            "Drop your TOMST TMS-4 export files here (one or more per sensor)",
            type=["csv"], accept_multiple_files=True, key=_UPLOAD_KEY,
            help="Standard TOMST export naming: data_<sensor serial>_<yyyy>_<mm>_<dd>_<part>.csv. Multiple "
                 "downloads of the same physical sensor are grouped and merged automatically.",
        )
    else:
        uploaded_files = st.session_state.get(_UPLOAD_KEY)

    if uploaded_files:
        source_label = f"{len(uploaded_files)} uploaded file(s)"
        generic_looking = [f.name for f in uploaded_files if looks_like_generic_export(f.name, f.getvalue())]
        if generic_looking:
            st.error(f"{', '.join(generic_looking)} looks like the generic pipeline's format (phenomenon_time/"
                     "result), not a TOMST TMS-4 raw export - switch to the **Generic pipeline** above to process it.")
            st.stop()
        try:
            raw_wide = TMS.load_tms_raw_from_uploads(uploaded_files)
        except Exception as e:
            st.error(f"Could not parse the uploaded files: {e}")
            st.stop()
    else:
        try:
            data_dir = TMS.resolve_tms_data_dir()
        except FileNotFoundError as e:
            st.error(str(e))
            st.stop()
        source_label = str(data_dir)
        raw_wide = TMS.load_tms_raw(data_dir)

    if show_ui:
        st.caption(f"Data source: **{source_label}** - each step (see sidebar) shows the data before/after that stage.")

    r = get_tms_pipeline(
        raw_wide, get_table("metadata"), get_table("correction"), get_table("calibration"),
        get_table("field_events"), settings.qc_cfg, settings.final_qc_cfg, settings.step_min,
    )
    sensor_ids = sorted(raw_wide["sensor_id"].unique())
    sensors = SensorMeta(
        ids=sensor_ids, label={s: s for s in sensor_ids},
        color={s: CATEGORICAL_COLORS[i % len(CATEGORICAL_COLORS)] for i, s in enumerate(sensor_ids)},
    )
    return r, sensors
