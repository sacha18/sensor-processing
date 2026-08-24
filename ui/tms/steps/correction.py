"""Step 4: Sensor-specific signal correction - one-factor (older sensors) or
two-factor (newer sensors) correction applied to the QC'd raw Signal.
Parameters are supplied by your team, not derived by this app."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.charts import before_after_chart, plot
from ui.generic.data_source import SensorMeta
from ui.fullscreen import is_fullscreen
from ui.theme import CHANGED_HIGHLIGHT_COLOR
from ui.tms.config import (delete_row, example_csv, example_json, get_table, merge_uploaded,
                            parse_optional_datetime, set_table)

_SECTION = "tms_correction"


def _rule_summary(row: pd.Series) -> str:
    factors = f"a={row['factor_a']:g}" + (f", b={row['factor_b']:g}" if pd.notna(row.get("factor_b")) else "")
    window = ""
    if pd.notna(row.get("valid_from")) or pd.notna(row.get("valid_to")):
        window = f" - {row['valid_from'] if pd.notna(row['valid_from']) else '...'} → {row['valid_to'] if pd.notna(row['valid_to']) else '...'}"
    notes = f" - _{row['notes']}_" if row.get("notes") else ""
    return f"`{row['sensor_id'] or '*'}` - {row['correction_type']} ({factors}){window}{notes}"


def _render_rules(corrected: pd.DataFrame) -> None:
    uploaded = st.file_uploader("Upload correction params CSV/JSON", type=["csv", "json"], key="tms_correction_upload")
    with st.expander("Example file format", icon=":material/help:"):
        st.caption("Columns: `sensor_id` (blank or `*` = every sensor), `correction_type` "
                   "(`one_factor`/`two_factor`), `factor_a`, `factor_b` (two-factor only), "
                   "`valid_from`, `valid_to`, `notes`.")
        st.code(example_csv("correction"), language="csv")
        d1, d2 = st.columns(2)
        d1.download_button("Download example CSV", example_csv("correction"), file_name="correction_example.csv",
                            mime="text/csv", icon=":material/download:")
        d2.download_button("Download example JSON", example_json("correction"), file_name="correction_example.json",
                            mime="application/json", icon=":material/download:")
    if uploaded is not None and st.session_state.get("tms_correction_upload_name") != uploaded.name:
        n = merge_uploaded("correction", uploaded)
        st.session_state["tms_correction_upload_name"] = uploaded.name
        st.success(f"Added {n} row(s) from {uploaded.name}.")
        st.rerun()

    with st.form("tms_correction_add", clear_on_submit=True, border=True):
        st.write("**Add a correction rule**")
        c1, c2, c3, c4 = st.columns(4)
        sensor_id = c1.text_input("Sensor or group", placeholder="*", help="Blank or \"*\" = every sensor.")
        correction_type = c2.selectbox("Type", ["one_factor", "two_factor"])
        factor_a = c3.number_input("a", value=None, format="%.6g")
        factor_b = c4.number_input("b", value=None, format="%.6g", help="Two-factor only.")
        c5, c6, c7 = st.columns(3)
        valid_from = c5.text_input("Valid from", placeholder="blank = always", help="e.g. 2025-06-01 or 2025-06-01 14:00")
        valid_to = c6.text_input("Valid to", placeholder="blank = always")
        notes = c7.text_input("Notes")
        if st.form_submit_button("Add rule", icon=":material/add_circle:", type="primary"):
            if factor_a is None:
                st.error("\"a\" is required.")
            else:
                vf, vt = parse_optional_datetime(valid_from), parse_optional_datetime(valid_to)
                if vf is False or vt is False:
                    st.error("Couldn't parse Valid from/to - try e.g. 2025-06-01 or 2025-06-01 14:00.")
                else:
                    new_row = pd.DataFrame([{
                        "sensor_id": sensor_id.strip() or "*", "correction_type": correction_type,
                        "factor_a": factor_a, "factor_b": factor_b, "valid_from": vf, "valid_to": vt,
                        "notes": notes.strip() or None,
                    }])
                    set_table("correction", pd.concat([get_table("correction"), new_row], ignore_index=True))
                    st.rerun()

    table = get_table("correction")
    if table.empty:
        st.caption("No correction rules yet - add one above, or upload a file.")
    else:
        st.write(f"**{len(table)} rule(s)**")
        for i, row in table.iterrows():
            c1, c2 = st.columns([6, 1])
            c1.markdown(_rule_summary(row))
            if c2.button("Delete", key=f"del_correction_{i}", icon=":material/delete:"):
                delete_row("correction", i)
                st.rerun()

    n_missing = int(corrected["is_qc_missing_correction_params"].sum())
    if n_missing:
        st.warning(f"{n_missing} reading(s) have no matching correction parameters - left uncorrected (NA).")


def render(r: dict, sensors: SensorMeta) -> None:
    corrected = r["corrected"]
    fullscreen = is_fullscreen(_SECTION)

    if not fullscreen:
        st.subheader("Correction parameters", divider="gray")
        st.caption("Supplied by your team, per sensor or sensor group (matched via the metadata **Group** column) - "
                   "not derived by this app. One-factor: `a x Signal`. Two-factor: `a x Signal + b`. "
                   "Sensor = \"*\" applies to every sensor.")
        _render_rules(corrected)

    st.write("**Before / after - QC'd Signal vs. corrected Signal**")
    sensor = st.selectbox("Sensor", sensors.ids, format_func=lambda s: sensors.label[s], key="tms_correction_sensor")
    sub = corrected[corrected["sensor_id"] == sensor].sort_values("timestamp")
    fig, changed = before_after_chart(
        sub["timestamp"], sub["signal_qc"], sub["signal_corrected"],
        after_color=sensors.color[sensor], changed_color=CHANGED_HIGHLIGHT_COLOR,
        before_name="QC'd Signal", after_name="corrected", changed_name="changed by correction",
    )
    if changed.any():
        st.caption(f"{int(changed.sum())} reading(s) changed by correction for this sensor - "
                   "changed region(s) marked above (start/end only, for long unbroken runs).")
    else:
        st.caption("Correction leaves this sensor's values unchanged (identity params, or nothing matched yet).")
    plot(fig)
