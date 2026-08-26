"""Session-state-backed config tables for the TMS pipeline: deployment
metadata, sensor-specific correction/calibration parameters, and manually
logged field events. Each table can be prefilled by uploading a CSV/JSON
file and/or edited directly in the UI (st.data_editor in ui/tms/steps/*) -
mirrors the store()/get/set pattern in ui/generic/settings.py, just for a
table instead of a scalar dict.
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pandas as pd
import streamlit as st

_DATE_COLS = {"install_start", "install_end", "valid_from", "valid_to", "start", "end", "created_at"}
_NUMERIC_PREFIXES = ("coef_",)
_NUMERIC_COLS = {"factor_a", "factor_b", "depth_cm"}

_SCHEMAS = {
    "metadata": {
        "session_key": "tms_metadata_df",
        "columns": ["sensor_id", "group_key", "site", "treatment", "position", "position_depth",
                    "row", "transect", "depth_cm", "t1_label", "t2_label", "t3_label",
                    "install_start", "install_end", "notes"],
    },
    "correction": {
        "session_key": "tms_correction_df",
        "columns": ["sensor_id", "correction_type", "factor_a", "factor_b",
                    "valid_from", "valid_to", "notes"],
    },
    "calibration": {
        "session_key": "tms_calibration_df",
        "columns": ["sensor_id", "coef_0", "coef_1", "coef_2", "coef_3", "coef_4", "coef_5",
                    "valid_from", "valid_to", "notes"],
    },
    "field_events": {
        "session_key": "tms_field_events_df",
        # sensor_id/treatment blank or "*"/"all" = wildcard (applies to every
        # sensor, or every sensor of that treatment) - see pipeline/tms/events.py.
        # edit_id/created_by/created_at are only populated for a row added through
        # the manual QC editor (ui/tms/steps/final_qc.py) - a bulk CSV/JSON upload
        # or a direct data_editor row leaves them blank. edit_id groups the one or
        # more rows a single "mark interval invalid" action produced (e.g. several
        # channels at once) so they can be reviewed/reverted together.
        "columns": ["sensor_id", "treatment", "channel", "start", "end", "event_type", "note",
                    "edit_id", "created_by", "created_at"],
    },
}


def _is_numeric_col(col: str) -> bool:
    return col in _NUMERIC_COLS or col.startswith(_NUMERIC_PREFIXES)


def _normalize_header(h) -> str:
    return re.sub(r"[\s_]+", "_", str(h).strip().lower())


def _coerce(name: str, df: pd.DataFrame) -> pd.DataFrame:
    cols = _SCHEMAS[name]["columns"]
    # an uploaded file's headers are free text (e.g. "Treatment", "Sensor ID") -
    # not guaranteed to match this app's own lowercase/underscored column names
    # byte-for-byte. Match case/whitespace-insensitively and rename onto the
    # schema's own names before reindexing - a case-sensitive reindex alone
    # would otherwise silently drop a mismatched column to an all-NaN one
    # (e.g. a "Treatment" header's data never reaching the "treatment" column,
    # even though it parsed and was right there).
    incoming = {_normalize_header(c): c for c in df.columns}
    rename = {incoming[c]: c for c in cols if c in incoming}
    df = df.rename(columns=rename).reindex(columns=cols)
    for c in cols:
        if c in _DATE_COLS:
            df[c] = pd.to_datetime(df[c], errors="coerce")
        elif _is_numeric_col(c):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            # explicit str(), not just .astype("object") - a CSV's all-numeric
            # sensor_id column round-trips as Python ints inside an object
            # column, which pyarrow still infers as an integer array, clashing
            # with the TextColumn config the editors below declare for it
            df[c] = df[c].apply(lambda v: None if pd.isna(v) else str(v))
    return df.reset_index(drop=True)


def _empty_table(name: str) -> pd.DataFrame:
    return _coerce(name, pd.DataFrame(columns=_SCHEMAS[name]["columns"]))


# Sample rows shown as an importable CSV/JSON example next to the "correction"
# and "calibration" upload widgets - same columns _SCHEMAS expects, so a
# downloaded copy round-trips straight through merge_uploaded() unchanged.
_EXAMPLE_ROWS = {
    "correction": [
        {"sensor_id": "*", "correction_type": "one_factor", "factor_a": 1.0, "factor_b": None,
         "valid_from": None, "valid_to": None, "notes": "identity (no-op), applies to every sensor"},
        {"sensor_id": "95648949", "correction_type": "two_factor", "factor_a": 0.0125, "factor_b": -0.15,
         "valid_from": "2025-06-01", "valid_to": None, "notes": "two-factor override for one sensor"},
    ],
    "calibration": [
        {"sensor_id": "*", "coef_0": -0.101168511, "coef_1": 0.000118119, "coef_2": 0.000000017,
         "coef_3": None, "coef_4": None, "coef_5": None,
         "valid_from": None, "valid_to": None, "notes": "TOMST universal calibration"},
        {"sensor_id": "95648949", "coef_0": -0.15, "coef_1": 0.00015, "coef_2": None, "coef_3": None,
         "coef_4": None, "coef_5": None,
         "valid_from": None, "valid_to": None, "notes": "sensor-specific override"},
    ],
}


def example_csv(name: str) -> str:
    return pd.DataFrame(_EXAMPLE_ROWS[name]).to_csv(index=False)


def example_json(name: str) -> str:
    return json.dumps(_EXAMPLE_ROWS[name], indent=2)


def init_tms_config() -> None:
    for name in _SCHEMAS:
        st.session_state.setdefault(_SCHEMAS[name]["session_key"], _empty_table(name))


def get_table(name: str) -> pd.DataFrame:
    return st.session_state[_SCHEMAS[name]["session_key"]]


def editor_key(name: str) -> str:
    """A st.data_editor `key` that changes every time the table is replaced
    (upload or Apply) - without this, a keyed data_editor keeps showing its
    own prior widget state on rerun and ignores the new `data` argument, so
    an upload would silently fail to appear in the editor."""
    return f"tms_{name}_editor_{st.session_state.get(f'_tms_{name}_version', 0)}"


def set_table(name: str, df: pd.DataFrame) -> None:
    st.session_state[_SCHEMAS[name]["session_key"]] = _coerce(name, df)
    version_key = f"_tms_{name}_version"
    st.session_state[version_key] = st.session_state.get(version_key, 0) + 1


def parse_uploaded(uploaded_file, skiprows: int = 0) -> pd.DataFrame:
    """`skiprows` lets the caller skip title/notes rows sitting above the
    real header - only meaningful for row-oriented formats (CSV/XLSX), not
    JSON."""
    suffix = Path(uploaded_file.name).suffix.lower()
    content = uploaded_file.getvalue()
    if suffix == ".json":
        return pd.DataFrame(json.loads(content.decode("utf-8")))
    if suffix == ".xlsx":
        return pd.read_excel(io.BytesIO(content), skiprows=skiprows)
    return pd.read_csv(io.BytesIO(content), skiprows=skiprows)


def delete_row(name: str, index) -> None:
    """Removes one or more rows (by position in get_table(name), a single
    index or a list) - used by the per-row Delete button next to each rule
    in the "add a rule" forms, and by the manual QC editor's "Revert" button
    (a list, to drop every row one "mark invalid" action produced at once)."""
    set_table(name, get_table(name).drop(index=index))


def merge_rows(name: str, incoming: pd.DataFrame) -> int:
    """Appends already-parsed rows to the table (upload prefills, subsequent
    st.data_editor edits layer on top). Returns the number of rows added."""
    incoming = _coerce(name, incoming)
    merged = pd.concat([get_table(name), incoming], ignore_index=True).drop_duplicates()
    set_table(name, merged)
    return len(incoming)


def guess_column_mapping(name: str, df: pd.DataFrame) -> dict[str, str]:
    """Best-effort default mapping from each of `name`'s schema columns to a
    column in `df`, using the same case/whitespace-insensitive header match
    _coerce falls back to - a starting point for the explicit column-mapping
    selectors in the UI, not a substitute for them (an upload's headers are
    free text and won't always line up, e.g. "Depth of installation [cm]" vs
    "depth_cm")."""
    incoming = {_normalize_header(c): c for c in df.columns}
    return {c: incoming[c] for c in _SCHEMAS[name]["columns"] if c in incoming}


def merge_by_sensor(name: str, incoming: pd.DataFrame) -> tuple[int, int]:
    """Joins incoming rows onto the existing table by sensor_id, instead of
    appending: a sensor that already has exactly one row (e.g. seeded from
    the loaded raw data) gets that row's columns filled in from the incoming
    non-blank values, rather than gaining a second, mostly-duplicate row. A
    sensor with zero or more than one existing row is ambiguous to update
    unambiguously, so it's appended instead. Returns (rows appended, rows
    updated)."""
    incoming = _coerce(name, incoming)
    current = get_table(name).copy()
    if current.empty or "sensor_id" not in current.columns:
        set_table(name, pd.concat([current, incoming], ignore_index=True))
        return len(incoming), 0

    counts = current["sensor_id"].value_counts()
    updated = 0
    to_append = []
    for _, row in incoming.iterrows():
        sid = row["sensor_id"]
        if counts.get(sid) == 1:
            idx = current.index[current["sensor_id"] == sid][0]
            for col, val in row.items():
                if col == "sensor_id" or pd.isna(val):
                    continue
                current.at[idx, col] = val
            updated += 1
        else:
            to_append.append(row)
    if to_append:
        current = pd.concat([current, pd.DataFrame(to_append)], ignore_index=True)
    set_table(name, current)
    return len(to_append), updated


def merge_uploaded(name: str, uploaded_file, skiprows: int = 0) -> int:
    """Parses an uploaded CSV/JSON/XLSX and appends its rows to the table.
    Returns the number of rows added."""
    return merge_rows(name, parse_uploaded(uploaded_file, skiprows))
