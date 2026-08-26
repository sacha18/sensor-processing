"""Step 2: Metadata assignment - deployment metadata (site, treatment,
position, depth, install period, channel labels) is attached per sensor and
install period; readings outside every configured install period are
excluded from the working series and reported separately, not silently
dropped."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import streamlit as st

from pipeline.tms.config import NEAR_SURFACE_LABELS, NEAR_SURFACE_POSITION
from ui.format import to_csv_bytes
from ui.tms.config import editor_key, get_table, guess_column_mapping, merge_by_sensor, parse_uploaded, set_table

_DONT_IMPORT = "Don't import"

# column -> display label, shared between the data_editor's column_config and
# the "imported" marker appended to a column last populated by an upload -
# keeping the two tables from before merged into a single one meant the
# highlight has to live on this table's own column headers instead.
_COLUMN_LABELS = {
    "sensor_id": "Sensor",
    "group_key": "Group",
    "site": "Site",
    "treatment": "Treatment",
    "position": "Position",
    "position_depth": "Position (depth)",
    "row": "Row",
    "transect": "Transect",
    "depth_cm": "Depth (cm)",
    "t1_label": "T1 label",
    "t2_label": "T2 label",
    "t3_label": "T3 label",
    "install_start": "Install start",
    "install_end": "Install end",
    "notes": "Notes",
}


def _label(col: str, merged_cols: set[str]) -> str:
    base = _COLUMN_LABELS[col]
    return f"{base} \U0001f4e5" if col in merged_cols else base


def _guess_sensor_col(columns: list[str]) -> int:
    """Best-effort default for the sensor-id column selector below - an
    upload's header naming it "sensor_id" outright is the common case, "id"
    aliases when it doesn't, otherwise leave the choice to the user rather
    than guessing wrong and silently joining on the wrong column."""
    normalized = [re.sub(r"[\s_]+", "_", str(c).strip().lower()) for c in columns]
    for target in ("sensor_id", "sensor", "id"):
        if target in normalized:
            return normalized.index(target)
    return 0


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
            columns = list(preview.columns)
            sensor_col = st.selectbox(
                "Sensor ID column", columns, index=_guess_sensor_col(columns), key="tms_metadata_sensor_col",
                help="Which column in this file holds the TOMST sensor serial number - used to join each row "
                     "onto a sensor in the table below and to skip rows for sensors that haven't been loaded yet.")

            st.caption(
                "Map the file's other columns onto each field below - only needed where the file's own header "
                "doesn't already match (e.g. \"Depth of installation [cm]\" won't auto-match \"Depth (cm)\"). "
                "Leave \"Don't import\" for a field the file doesn't have.")
            guessed = guess_column_mapping("metadata", preview)
            options = [_DONT_IMPORT] + columns
            mappable = [c for c in _COLUMN_LABELS if c != "sensor_id"]
            field_cols = st.columns(4)
            col_mapping = {}
            for i, field in enumerate(mappable):
                default = guessed.get(field)
                default_idx = options.index(default) if default in options else 0
                with field_cols[i % 4]:
                    choice = st.selectbox(
                        _COLUMN_LABELS[field], options, index=default_idx, key=f"tms_metadata_map_{field}")
                if choice != _DONT_IMPORT:
                    col_mapping[choice] = field

            imported_ids = set(r["raw_wide"]["sensor_id"].astype(str)) if not r["raw_wide"].empty else set()
            # col_mapping keys are the file's own column names, so this merges cleanly
            # with the sensor_id mapping below and restricts `joined` to exactly the
            # columns picked above - a field left "Don't import" must stay out, not get
            # silently pulled back in by _coerce's own fuzzy header matching downstream.
            rename = {sensor_col: "sensor_id", **col_mapping}
            joined = preview[list(rename.keys())].rename(columns=rename)
            matched = joined[joined["sensor_id"].astype(str).isin(imported_ids)]
            skipped = len(joined) - len(matched)
            # applies once per distinct (file, header row, mapping) rather than on every
            # rerun - a data_editor edit or an unrelated widget interaction reruns this
            # whole script too, which would otherwise silently re-merge the same file
            # over and over as long as the uploader still holds it.
            merge_key = (uploaded.name, uploaded.size, skip_rows, sensor_col, tuple(sorted(col_mapping.items())))
            if st.session_state.get("_tms_metadata_merge_key") != merge_key:
                added, updated = merge_by_sensor("metadata", matched)
                st.session_state["_tms_metadata_merge_key"] = merge_key
                st.session_state["_tms_metadata_merged_cols"] = set(col_mapping.values())
                st.session_state["_tms_metadata_merge_feedback"] = (added, updated, skipped, uploaded.name)
                st.rerun()

    feedback = st.session_state.pop("_tms_metadata_merge_feedback", None)
    if feedback:
        added, updated, skipped, name = feedback
        st.success(f"Updated {updated} existing row(s) and added {added} new row(s) from {name}.")
        if skipped:
            st.warning(f"Skipped {skipped} row(s) whose sensor ID doesn't match any loaded sensor.")

    merged_cols = st.session_state.get("_tms_metadata_merged_cols", set())
    caption = "Final metadata table - this is what the pipeline uses. Edit directly if needed, then Apply."
    if merged_cols:
        caption += " \U0001f4e5 marks a column last filled in from an uploaded file."
    st.caption(caption)
    edited = st.data_editor(
        get_table("metadata"), num_rows="dynamic", width='stretch', key=editor_key("metadata"),
        column_config={
            "sensor_id": st.column_config.TextColumn(
                _label("sensor_id", merged_cols), required=True,
                help="TOMST serial number (e.g. 94951005) - the key linking everything for this sensor: raw "
                     "files, correction/calibration rules, and readings."),
            "group_key": st.column_config.TextColumn(
                _label("group_key", merged_cols),
                help="Optional - lets correction/calibration params apply to a group of sensors at once."),
            "site": st.column_config.TextColumn(_label("site", merged_cols)),
            "treatment": st.column_config.TextColumn(
                _label("treatment", merged_cols),
                help="The experimental treatment being compared, e.g. \"Tree alley\" vs \"Crop field\" - the "
                     "main variable of the study."),
            "position": st.column_config.TextColumn(
                _label("position", merged_cols),
                help="Compact location code, e.g. \"3A,2T\" = alley 3, transect 2."),
            "position_depth": st.column_config.TextColumn(
                _label("position_depth", merged_cols),
                help="Position with depth appended for a readable label, e.g. \"3A,2T [14]\" - derived from "
                     "Position + Depth, not an independent value."),
            "row": st.column_config.TextColumn(
                _label("row", merged_cols),
                help="Physical alley/strip or plot row, e.g. 1A-3A for tree alleys, 1S-4S for crop strips - "
                     "one axis of spatial replication."),
            "transect": st.column_config.TextColumn(
                _label("transect", merged_cols),
                help="Position along the row (e.g. 1, 2, or 3) - second replication axis; each row x transect "
                     "combination is one measurement point."),
            "depth_cm": st.column_config.NumberColumn(
                _label("depth_cm", merged_cols),
                help="Installation depth, e.g. 14 (standard near-surface), 25, or 50 - determines how to "
                     "interpret T1/T2/T3 and which soil layer the moisture signal measures. Magnitude is what "
                     "matters; sign is not significant."),
            "t1_label": st.column_config.TextColumn(_label("t1_label", merged_cols)),
            "t2_label": st.column_config.TextColumn(_label("t2_label", merged_cols)),
            "t3_label": st.column_config.TextColumn(_label("t3_label", merged_cols)),
            "install_start": st.column_config.DatetimeColumn(
                _label("install_start", merged_cols),
                help="Date the sensor was placed in the field - readings before this are excluded (a sensor "
                     "logs while still in storage/transit, before being planted)."),
            "install_end": st.column_config.DatetimeColumn(
                _label("install_end", merged_cols), help="Blank = still deployed."),
            "notes": st.column_config.TextColumn(_label("notes", merged_cols)),
        },
    )
    if st.button("Save table edits (only needed after editing cells directly above)", type="primary",
                 icon=":material/check_circle:",
                 help="File imports and the column mapping above are already saved automatically - this button "
                      "is only for changes you typed or deleted directly in the table's cells."):
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
