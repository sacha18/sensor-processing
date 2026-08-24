"""Step 5: Calibration to VWC - a polynomial equation in the corrected
Signal, supplied by your team per sensor or sensor group (not derived by
this app, and assignable via metadata rather than hardcoded)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from pipeline.tms.config import POLY_COEF_COLUMNS, TOMST_UNIVERSAL_CALIBRATION
from ui.charts import plot
from ui.generic.data_source import SensorMeta
from ui.fullscreen import is_fullscreen
from ui.theme import CHANGED_HIGHLIGHT_COLOR, HORIZONTAL_LEGEND
from ui.tms.config import (delete_row, example_csv, example_json, get_table, merge_uploaded,
                            parse_optional_datetime, set_table)

_SECTION = "tms_calibration"


def _rule_summary(row: pd.Series) -> str:
    coefs = ", ".join(f"{c}={row[c]:.3e}" for c in POLY_COEF_COLUMNS if pd.notna(row.get(c)))
    window = ""
    if pd.notna(row.get("valid_from")) or pd.notna(row.get("valid_to")):
        window = f" - {row['valid_from'] if pd.notna(row['valid_from']) else '...'} → {row['valid_to'] if pd.notna(row['valid_to']) else '...'}"
    notes = f" - _{row['notes']}_" if row.get("notes") else ""
    return f"`{row['sensor_id'] or '*'}` - {coefs}{window}{notes}"


def _render_rules(calibrated: pd.DataFrame) -> None:
    uploaded = st.file_uploader("Upload calibration params CSV/JSON", type=["csv", "json"], key="tms_calibration_upload")
    with st.expander("Example file format", icon=":material/help:"):
        st.caption("Columns: `sensor_id` (blank or `*` = every sensor), `coef_0`..`coef_5` (polynomial "
                   "coefficients, `coef_0` required, leave higher orders blank for a lower-degree equation), "
                   "`valid_from`, `valid_to`, `notes`.")
        st.code(example_csv("calibration"), language="csv")
        d1, d2 = st.columns(2)
        d1.download_button("Download example CSV", example_csv("calibration"), file_name="calibration_example.csv",
                            mime="text/csv", icon=":material/download:")
        d2.download_button("Download example JSON", example_json("calibration"), file_name="calibration_example.json",
                            mime="application/json", icon=":material/download:")
    if uploaded is not None and st.session_state.get("tms_calibration_upload_name") != uploaded.name:
        n = merge_uploaded("calibration", uploaded)
        st.session_state["tms_calibration_upload_name"] = uploaded.name
        st.success(f"Added {n} row(s) from {uploaded.name}.")
        st.rerun()

    if st.button("Fill in TOMST's universal calibration", icon=":material/auto_fix_high:",
                 help="Adds one sensor_id=\"*\" row with TOMST's published quadratic calibration "
                      f"(coef_0={TOMST_UNIVERSAL_CALIBRATION['coef_0']}, coef_1={TOMST_UNIVERSAL_CALIBRATION['coef_1']}, "
                      f"coef_2={TOMST_UNIVERSAL_CALIBRATION['coef_2']}) - edit or delete it below if your team's is different."):
        universal_row = pd.DataFrame([{"sensor_id": "*", **TOMST_UNIVERSAL_CALIBRATION, "notes": "TOMST universal calibration"}])
        set_table("calibration", pd.concat([get_table("calibration"), universal_row], ignore_index=True))
        st.rerun()

    with st.form("tms_calibration_add", clear_on_submit=True, border=True):
        st.write("**Add a calibration rule**")
        c1, c2 = st.columns([2, 1])
        sensor_id = c1.text_input("Sensor or group", placeholder="*", help="Blank or \"*\" = every sensor.")
        valid_from = c2.text_input("Valid from", placeholder="blank = always", help="e.g. 2025-06-01 or 2025-06-01 14:00")
        coef_values = {}
        coef_cols = st.columns(len(POLY_COEF_COLUMNS))
        for col, c in zip(POLY_COEF_COLUMNS, coef_cols):
            coef_values[col] = c.number_input(col, value=None, format="%.6g", key=f"tms_cal_add_{col}")
        c3, c4 = st.columns(2)
        valid_to = c3.text_input("Valid to", placeholder="blank = always")
        notes = c4.text_input("Notes")
        if st.form_submit_button("Add rule", icon=":material/add_circle:", type="primary"):
            if coef_values["coef_0"] is None:
                st.error("coef_0 is required (the constant term - at least a flat calibration needs it).")
            else:
                vf, vt = parse_optional_datetime(valid_from), parse_optional_datetime(valid_to)
                if vf is False or vt is False:
                    st.error("Couldn't parse Valid from/to - try e.g. 2025-06-01 or 2025-06-01 14:00.")
                else:
                    new_row = pd.DataFrame([{
                        "sensor_id": sensor_id.strip() or "*", **coef_values,
                        "valid_from": vf, "valid_to": vt, "notes": notes.strip() or None,
                    }])
                    set_table("calibration", pd.concat([get_table("calibration"), new_row], ignore_index=True))
                    st.rerun()

    table = get_table("calibration")
    if table.empty:
        st.caption("No calibration rules yet - add one above, use the TOMST default, or upload a file.")
    else:
        st.write(f"**{len(table)} rule(s)**")
        for i, row in table.iterrows():
            c1, c2 = st.columns([6, 1])
            c1.markdown(_rule_summary(row))
            if c2.button("Delete", key=f"del_calibration_{i}", icon=":material/delete:"):
                delete_row("calibration", i)
                st.rerun()

    n_missing = int(calibrated["is_qc_missing_calibration_params"].sum())
    if n_missing:
        st.warning(f"{n_missing} reading(s) have no matching calibration parameters - VWC left blank (NA).")


def render(r: dict, sensors: SensorMeta) -> None:
    calibrated = r["calibrated"]
    fullscreen = is_fullscreen(_SECTION)

    if not fullscreen:
        st.subheader("Calibration parameters", divider="gray")
        st.caption("Supplied by your team, per sensor or sensor group - VWC = polynomial in corrected Signal "
                   "(coef_0 = constant term). Leave higher-order coefficients blank for a lower-degree equation "
                   "(e.g. only coef_0/coef_1 set = a straight line). Sensor = \"*\" applies to every sensor - useful "
                   "since TOMST's own calibration is one universal equation, not one per sensor.")
        _render_rules(calibrated)

    st.write("**Corrected Signal -> VWC**")
    sensor = st.selectbox("Sensor", sensors.ids, format_func=lambda s: sensors.label[s], key="tms_calibration_sensor")
    sub = calibrated[calibrated["sensor_id"] == sensor].sort_values("timestamp").dropna(subset=["signal_corrected", "vwc"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sub["signal_corrected"], y=sub["vwc"], mode="markers",
                              marker=dict(color=sensors.color[sensor], size=4, opacity=0.5), name="readings"))
    fig.update_layout(height=380, margin=dict(t=40), xaxis_title="Corrected Signal", yaxis_title="VWC", legend=HORIZONTAL_LEGEND)
    plot(fig)

    st.write("**VWC time series**")
    full = calibrated[calibrated["sensor_id"] == sensor].sort_values("timestamp")
    missing = full[full["is_qc_missing_calibration_params"]]
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=full["timestamp"], y=full["vwc"], mode="lines", line=dict(color=sensors.color[sensor]), name="VWC"))
    if len(missing):
        # calibration's "difference" isn't a like-for-like value change (Signal
        # and VWC are different units) - it's a gap it introduces where a
        # corrected Signal exists but no calibration params matched. Ticks along
        # the top mark exactly where, instead of a same-axis before/after line.
        top = float(full["vwc"].max()) if full["vwc"].notna().any() else 0.0
        fig2.add_trace(go.Scatter(x=missing["timestamp"], y=[top] * len(missing), mode="markers",
                                   marker=dict(symbol="line-ns", color=CHANGED_HIGHLIGHT_COLOR, size=14, line=dict(width=2)),
                                   name="missing calibration params"))
    fig2.update_layout(height=320, margin=dict(t=40), legend=HORIZONTAL_LEGEND)
    plot(fig2)
    if len(missing):
        st.caption(f"{len(missing)} timestamp(s) highlighted above have a corrected Signal but no VWC - "
                   "no matching calibration parameters for this sensor/time range.")
