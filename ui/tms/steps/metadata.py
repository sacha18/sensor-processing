"""Step 2: Metadata assignment - deployment metadata (site, treatment,
position, depth, install period, channel labels) is attached per sensor and
install period; readings outside every configured install period are
excluded from the working series and reported separately, not silently
dropped."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from pipeline.tms.config import NEAR_SURFACE_LABELS, NEAR_SURFACE_POSITION
from ui.format import to_csv_bytes
from ui.tms.config import editor_key, get_table, merge_uploaded, parse_uploaded, set_table


def _seed_from_loaded_sensors(r: dict) -> None:
    """The first time this step is opened in a session, pre-fill one row per
    sensor_id already present in the loaded raw data - sensor_id and the
    first-observed timestamp (as an install_start starting guess) come
    straight from the data; position/T1-T3 labels default to TOMST's
    standard near-surface convention as an editable suggestion, not an
    assumption baked into the pipeline. Every value here is just a starting
    point the user reviews/edits - typing the id from scratch is what a typo
    would silently exclude that sensor's data with no error."""
    if st.session_state.get("_tms_metadata_seeded"):
        return
    st.session_state["_tms_metadata_seeded"] = True
    if not get_table("metadata").empty:
        return
    raw = r["raw_wide"]
    if raw.empty:
        return
    first_seen = raw.groupby(raw["sensor_id"].astype(str))["timestamp"].min()
    seed = pd.DataFrame({"sensor_id": sorted(first_seen.index)})
    seed["position"] = NEAR_SURFACE_POSITION
    for col, label in NEAR_SURFACE_LABELS.items():
        seed[col] = label
    seed["install_start"] = seed["sensor_id"].map(first_seen)
    set_table("metadata", seed)


def render(r: dict) -> None:
    _seed_from_loaded_sensors(r)

    st.subheader("Deployment metadata", divider="gray")

    uploaded = st.file_uploader(
        "Upload metadata CSV/JSON/XLSX", type=["csv", "json", "xlsx"], key="tms_metadata_upload",
        help="One row per sensor per install period (a logger can be redeployed) - site, treatment, position, "
             "depth, and the channel labels for a non-standard installation (T1/T2/T3's usual near-surface "
             "meaning doesn't hold for a deeper install). Pre-filled below with the sensors already loaded, "
             "each sensor's first observed timestamp as a starting install start, and the standard near-surface "
             "position/channel labels as a suggestion - correct any sensor installed differently. Upload to "
             "prefill more, then edit directly; hit Apply to use the edited table.")
    if uploaded is not None:
        skip_rows = 0
        if Path(uploaded.name).suffix.lower() in (".csv", ".xlsx"):
            header_row = st.number_input(
                "Header row", min_value=1, value=1, step=1, key="tms_metadata_header_row",
                help="1-indexed row where the column headers actually start - rows above it (title, notes, "
                     "merged cells) are skipped.")
            skip_rows = header_row - 1
        try:
            preview = parse_uploaded(uploaded, skip_rows)
        except Exception as e:
            st.error(f"Could not parse {uploaded.name}: {e}")
        else:
            st.dataframe(preview.head(5), width='stretch')
            if st.button(f"Import {len(preview)} row(s) from {uploaded.name}", icon=":material/publish:"):
                n = merge_uploaded("metadata", uploaded, skip_rows)
                st.success(f"Added {n} row(s) from {uploaded.name}.")
                st.rerun()

    edited = st.data_editor(
        get_table("metadata"), num_rows="dynamic", width='stretch', key=editor_key("metadata"),
        column_config={
            "sensor_id": st.column_config.TextColumn(
                "Sensor", required=True,
                help="TOMST serial number (e.g. 94951005) - the key linking everything for this sensor: raw "
                     "files, correction/calibration rules, and readings."),
            "group_key": st.column_config.TextColumn("Group", help="Optional - lets correction/calibration params apply to a group of sensors at once."),
            "treatment": st.column_config.TextColumn(
                "Treatment",
                help="The experimental treatment being compared, e.g. \"Tree alley\" vs \"Crop field\" - the "
                     "main variable of the study."),
            "position": st.column_config.TextColumn(
                "Position",
                help="Compact location code, e.g. \"3A,2T\" = alley 3, transect 2."),
            "position_depth": st.column_config.TextColumn(
                "Position (depth)",
                help="Position with depth appended for a readable label, e.g. \"3A,2T [14]\" - derived from "
                     "Position + Depth, not an independent value."),
            "row": st.column_config.TextColumn(
                "Row",
                help="Physical alley/strip or plot row, e.g. 1A-3A for tree alleys, 1S-4S for crop strips - "
                     "one axis of spatial replication."),
            "transect": st.column_config.TextColumn(
                "Transect",
                help="Position along the row (e.g. 1, 2, or 3) - second replication axis; each row x transect "
                     "combination is one measurement point."),
            "depth_cm": st.column_config.NumberColumn(
                "Depth (cm)",
                help="Installation depth, e.g. 14 (standard near-surface), 25, or 50 - determines how to "
                     "interpret T1/T2/T3 and which soil layer the moisture signal measures. Magnitude is what "
                     "matters; sign is not significant."),
            "install_start": st.column_config.DatetimeColumn(
                "Install start",
                help="Date the sensor was placed in the field - readings before this are excluded (a sensor "
                     "logs while still in storage/transit, before being planted)."),
            "install_end": st.column_config.DatetimeColumn("Install end", help="Blank = still deployed."),
        },
    )
    if st.button("Apply metadata", type="primary", icon=":material/check_circle:"):
        set_table("metadata", edited)
        st.rerun()

    st.subheader("Readings outside any installation period", divider="gray")
    excluded = r["excluded_metadata"]
    if excluded.empty:
        st.success("Every reading falls inside a configured install period.")
    else:
        st.warning(f"{len(excluded)} reading(s) excluded from the working series - no metadata row covers their timestamp.")
        st.dataframe(excluded.groupby(["sensor_id", "reason"]).size().reset_index(name="n_rows"), width='stretch')
        st.download_button("Download excluded rows CSV", to_csv_bytes(excluded, index=False),
                            file_name="tms_excluded_outside_install.csv", mime="text/csv", icon=":material/download:")
