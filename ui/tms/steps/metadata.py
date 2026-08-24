"""Step 2: Metadata assignment - deployment metadata (site, treatment,
position, depth, install period, channel labels) is attached per sensor and
install period; readings outside every configured install period are
excluded from the working series and reported separately, not silently
dropped."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from pipeline.tms.config import NEAR_SURFACE_LABELS, NEAR_SURFACE_POSITION
from ui.format import to_csv_bytes
from ui.tms.config import editor_key, get_table, merge_uploaded, set_table


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
        "Upload metadata CSV/JSON", type=["csv", "json"], key="tms_metadata_upload",
        help="One row per sensor per install period (a logger can be redeployed) - site, treatment, position, "
             "depth, and the channel labels for a non-standard installation (T1/T2/T3's usual near-surface "
             "meaning doesn't hold for a deeper install). Pre-filled below with the sensors already loaded, "
             "each sensor's first observed timestamp as a starting install start, and the standard near-surface "
             "position/channel labels as a suggestion - correct any sensor installed differently. Upload to "
             "prefill more, then edit directly; hit Apply to use the edited table.")
    if uploaded is not None and st.session_state.get("tms_metadata_upload_name") != uploaded.name:
        n = merge_uploaded("metadata", uploaded)
        st.session_state["tms_metadata_upload_name"] = uploaded.name
        st.success(f"Added {n} row(s) from {uploaded.name}.")
        st.rerun()

    edited = st.data_editor(
        get_table("metadata"), num_rows="dynamic", width='stretch', key=editor_key("metadata"),
        column_config={
            "sensor_id": st.column_config.TextColumn("Sensor", required=True),
            "group_key": st.column_config.TextColumn("Group", help="Optional - lets correction/calibration params apply to a group of sensors at once."),
            "position_depth": st.column_config.TextColumn("Position (depth)", help="E.g. a named depth class distinct from the free-text Position column."),
            "row": st.column_config.TextColumn("Row", help="Alley/strip or plot row, for trial designs organized that way."),
            "transect": st.column_config.TextColumn("Transect"),
            "depth_cm": st.column_config.NumberColumn("Depth (cm)", help="Negative = below surface."),
            "install_start": st.column_config.DatetimeColumn("Install start"),
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
