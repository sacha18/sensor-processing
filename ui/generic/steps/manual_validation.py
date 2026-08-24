"""Step 4 (part 2/2): Manual validation - review/override pipeline suggestions.

Rendered below ui.steps.outliers on the combined "Outliers & validation" step,
so detection and review live on the same screen.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui.charts import plot
from ui.generic.data_source import SensorMeta
from ui.theme import COLORS, HORIZONTAL_LEGEND, REFERENCE_LINE_COLOR

# readable labels for a raw fill_method value, so the filter reads e.g.
# "Correlated-series imputation (outlier)" instead of "outlier_donor_regression".
# note: a point keeps its original category here even once validated (this
# table is built before the commit patch below re-applies for the run) -
# that's what lets you re-select the same filter afterwards to review/undo it
SOURCE_LABELS = {
    "outlier_donor_regression": "Correlated-series imputation (outlier)",
    "donor_regression": "Correlated-series imputation (long gap)",
    "linear_interp": "Linear interpolation",
    "unfilled": "Unfilled",
}


def render(r: dict, sensors: SensorMeta, overrides_applied_count: int) -> None:
    st.subheader("Manual validation", divider="gray")
    st.caption("Review each suggestion the pipeline made for a **suspect value** (flagged outlier) or **missing "
               "data** point, then hit **Validate** to commit your review into the production dataset used by "
               "every step below.")

    review_df = r["production"].loc[r["production"]["fill_method"] != "observed",
                                     ["sensor_id", "timestamp", "is_outlier", "value_raw", "fill_method", "value_clean"]].copy()
    review_df = review_df.rename(columns={"value_clean": "suggested_value"}).sort_values(["sensor_id", "timestamp"]).reset_index(drop=True)
    review_df["status"] = np.where(review_df["is_outlier"], "Suspect value", "Missing data")
    review_df["value_raw"] = review_df["value_raw"].round(3)
    review_df["suggested_value"] = review_df["suggested_value"].round(3)

    if review_df.empty:
        st.success("Nothing to validate - no suspect values or missing data with this configuration.")
    else:
        filtered_df = pd.DataFrame()
        edited = pd.DataFrame()

        with st.container(border=True):
            st.markdown("**1. Filter, review, validate**")
            st.caption(f"{int((review_df['status'] == 'Suspect value').sum())} suspect value(s), "
                       f"{int((review_df['status'] == 'Missing data').sum())} missing data point(s) in total.")

            source_options = sorted(review_df["fill_method"].unique(),
                                     key=lambda m: list(SOURCE_LABELS).index(m) if m in SOURCE_LABELS else 99)
            selected_sources = st.multiselect(
                "Filter by suggestion source", source_options, default=source_options,
                format_func=lambda m: SOURCE_LABELS.get(m, m),
                help="Narrow the table (and what Validate/Clear act on) down to one kind of suggestion - e.g. only "
                     "the correlated-series imputations - so you can review and commit that category on its own.")
            filtered_df = review_df[review_df["fill_method"].isin(selected_sources)].reset_index(drop=True).copy()
            filtered_df["decision"] = "Accept suggestion"
            filtered_df["custom_value"] = filtered_df["suggested_value"]

            if filtered_df.empty:
                st.info("No suspect values or missing data match this filter.")
            else:
                n_filter_validated = sum(1 for sid, ts in zip(filtered_df["sensor_id"], filtered_df["timestamp"])
                                          if (sid, ts) in st.session_state.manual_overrides)
                m1, m2 = st.columns(2)
                m1.metric("Matching filter", len(filtered_df))
                m2.metric("Already validated", f"{n_filter_validated}/{len(filtered_df)}")

                edited = st.data_editor(
                    filtered_df[["sensor_id", "timestamp", "status", "value_raw", "fill_method", "suggested_value", "decision", "custom_value"]],
                    key="outlier_manual_review", width='stretch', height=320, hide_index=True,
                    disabled=["sensor_id", "timestamp", "status", "value_raw", "fill_method", "suggested_value"],
                    column_config={
                        "sensor_id": "Sensor",
                        "timestamp": st.column_config.DatetimeColumn("Time series (timestamp)"),
                        "status": "Status",
                        "value_raw": st.column_config.NumberColumn("Suspect value", format="%.3f", help="Empty for missing data - there's no raw reading to show."),
                        "fill_method": st.column_config.TextColumn("Suggestion source", help="Raw pipeline label - see the filter above for the readable name."),
                        "suggested_value": st.column_config.NumberColumn("Suggestion for the correct value", format="%.3f"),
                        "decision": st.column_config.SelectboxColumn(
                            "Decision", options=["Accept suggestion", "Keep raw value", "Custom value", "Leave unfilled"], required=True),
                        "custom_value": st.column_config.NumberColumn("Custom value", format="%.3f", help="Used only when decision = Custom value."),
                    },
                )

                final_value = edited["suggested_value"].copy()
                final_value = final_value.mask(edited["decision"] == "Keep raw value", edited["value_raw"])
                final_value = final_value.mask(edited["decision"] == "Custom value", edited["custom_value"])
                final_value = final_value.mask(edited["decision"] == "Leave unfilled", np.nan)
                edited = edited.assign(final_value=final_value)
                # keys come from filtered_df (untouched), not the data_editor's own output - the timestamp
                # column is display-only there and its dtype on round-trip isn't a contract worth relying on
                row_keys = list(zip(filtered_df["sensor_id"], filtered_df["timestamp"]))

                n_overridden = int((edited["decision"] != "Accept suggestion").sum())

                b1, b2, b3 = st.columns([1, 1, 2], gap="small")
                validate_clicked = b1.button(f"Validate ({len(filtered_df)})", type="primary", icon=":material/check_circle:",
                                              help="Commit the table above - accepted suggestions and overrides alike - into the production dataset.")
                clear_clicked = b2.button("Clear", icon=":material/restart_alt:",
                                           help="Revert these rows back to the pipeline's automatic suggestions.")
                b3.caption(f"{n_overridden}/{len(edited)} overridden in this draft - not committed until you hit Validate.")

                if validate_clicked:
                    for key, fv in zip(row_keys, edited["final_value"]):
                        st.session_state.manual_overrides[key] = fv
                    st.success(f"Validated {len(edited)} point(s) - now applied to Gap filling / Production dataset / Analysis below.")
                    st.rerun()

                if clear_clicked:
                    for key in row_keys:
                        st.session_state.manual_overrides.pop(key, None)
                    st.info("Validation cleared for the rows above - reverted to the pipeline's automatic suggestions.")
                    st.rerun()

        if not filtered_df.empty:
            st.markdown(f"**2. Zoom into one sensor** - detail view of the {len(filtered_df)} row(s) above")
            # selectbox for direct jump + prev/next for fewer clicks browsing sequentially -
            # both drive the same widget state, prev/next just pre-seed it before the
            # selectbox is instantiated (the only point at which that's allowed)
            current = st.session_state.get("review_sensor_select")
            if current not in sensors.ids:
                current = sensors.ids[0]
                st.session_state["review_sensor_select"] = current
            nav_r_prev, nav_r_select, nav_r_next = st.columns([1, 6, 1], gap="small")
            if nav_r_prev.button("", icon=":material/chevron_left:", key="review_prev", help="Previous sensor"):
                st.session_state["review_sensor_select"] = sensors.ids[(sensors.ids.index(current) - 1) % len(sensors.ids)]
            if nav_r_next.button("", icon=":material/chevron_right:", key="review_next", help="Next sensor"):
                st.session_state["review_sensor_select"] = sensors.ids[(sensors.ids.index(current) + 1) % len(sensors.ids)]
            review_sensor = nav_r_select.selectbox("Sensor to review", sensors.ids, key="review_sensor_select",
                                                    label_visibility="collapsed")
            raw_sub = r["reg_long"][r["reg_long"]["sensor_id"] == review_sensor].sort_values("timestamp")
            sub_review = edited[edited["sensor_id"] == review_sensor].sort_values("timestamp")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=raw_sub["timestamp"], y=raw_sub["value_raw"], mode="lines", connectgaps=True,
                                      line=dict(color=REFERENCE_LINE_COLOR, dash="dot"), name="raw"))
            fig.add_trace(go.Scatter(x=sub_review["timestamp"], y=sub_review["suggested_value"], mode="markers",
                                      marker=dict(color=COLORS["donor_regression"], size=8, symbol="circle-open", line=dict(width=2)),
                                      name="pipeline suggestion"))
            fig.add_trace(go.Scatter(x=sub_review["timestamp"], y=sub_review["final_value"], mode="markers",
                                      marker=dict(color=COLORS["manual_validated"], size=9, symbol="diamond", line=dict(width=1, color="white")),
                                      name="validated value"))
            # legend below the plot, not above (y=1.04 like the multi-sensor charts) - there's
            # a title here, and the two overlap once the container gets narrow
            fig.update_layout(height=380, title=f"{sensors.label[review_sensor]} - manual validation", margin=dict(t=40),
                               legend={**HORIZONTAL_LEGEND, "y": -0.2})
            plot(fig)

    if overrides_applied_count:
        st.caption(f"**{overrides_applied_count} point(s) currently locked in from manual validation** - shown as "
                   "*manual_validated* (teal) in the Gap filling and Production dataset steps below.")
