"""Data source expander: upload/sample loading, channel selection, unit labels,
and the cached pipeline run.
"""
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

import pipeline as P
from ui.format import is_telemetry_channel
from ui.settings import Settings
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


def render_data_source(settings: Settings):
    """Renders the "Data source" expander and runs the pipeline on the selected
    channels. Returns (r, sensors, units) or calls st.stop() on error/empty selection."""
    # Collapsed by default so the stepper is the first thing on screen - the bundled
    # sample data loads with no input needed, so most visits never need to open this.
    with st.expander("Data source", icon=":material/upload_file:"):
        st.caption("No file? No problem - the bundled sample data loads automatically below.")
        uploaded_files = st.file_uploader(
            "Drop your sensor files here (one file per sensor)",
            type=["json", "csv"], accept_multiple_files=True,
            help="JSON or CSV, same columns either way: phenomenon_time, result (observation_id optional). "
                 "The filename (without extension) becomes that sensor's id.",
        )

        if uploaded_files:
            source_label = f"{len(uploaded_files)} uploaded file(s)"
            try:
                raw_long = P.load_raw_from_uploads(uploaded_files)
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
            raw_long = P.load_raw(data_dir)

        all_channel_ids = sorted(raw_long["sensor_id"].unique())
        default_channels = [s for s in all_channel_ids if not is_telemetry_channel(s)]

        col_ch, col_units = st.columns([3, 2])
        with col_ch:
            included_channels = st.multiselect(
                "Channels to include", all_channel_ids, default=default_channels,
                help="Device telemetry (battery, radio signal, enclosure temp/humidity, firmware version, ...) is "
                     "excluded by default - only real measurement channels feed the pipeline. Adjust if needed.",
            )
        with col_units:
            units_file = st.file_uploader(
                "Optional: unit labels per sensor", type=["json", "csv"], key="units_uploader",
                help="Different sensors rarely measure the same thing (a piezometer in cm, a flow gauge in L/s, "
                     "a scintillometer in W/m2, ...) - drop a small mapping file to label charts accordingly. "
                     "Display only, doesn't affect any computation. CSV with sensor_id,unit columns, or JSON "
                     "{\"sensor_id\": \"unit\"}.",
            )

        if not included_channels:
            st.error("No channels selected - pick at least one to run the pipeline.")
            st.stop()
        raw_long = raw_long[raw_long["sensor_id"].isin(included_channels)].reset_index(drop=True)

        units = {}
        if units_file is not None:
            try:
                units = P.parse_units_mapping(units_file.name, units_file.getvalue())
            except Exception as e:
                st.warning(f"Could not parse the unit mapping file: {e}")

        st.caption(f"Data source: **{source_label}** - each step (see sidebar) shows the data before/after that stage.")

        r = get_pipeline(raw_long, step_min=settings.step_min, outlier_cfg=settings.outlier_cfg, max_gap=settings.max_gap,
                          smooth_window=settings.smooth_window, smooth_method=settings.smooth_method,
                          use_donor_regression=settings.use_donor_regression, donor_min_corr=settings.donor_min_corr)
        sensor_ids = sorted(r["reg_long"]["sensor_id"].unique())
        sensors = SensorMeta(
            ids=sensor_ids,
            label={s: (f"{s} ({units[s]})" if units.get(s) else s) for s in sensor_ids},
            color={s: CATEGORICAL_COLORS[i % len(CATEGORICAL_COLORS)] for i, s in enumerate(sensor_ids)},
        )

    return r, sensors, units
