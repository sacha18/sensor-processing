"""Step 6: Gap filling - fill-method breakdown and cleaned series charts."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from ui.charts import decimate, facet_grid_before_after, plot
from ui.generic.data_source import SensorMeta
from ui.fullscreen import is_fullscreen
from ui.theme import COLORS, HORIZONTAL_LEGEND, REFERENCE_LINE_COLOR

_SECTION = "gapfill"


def _add_sensor_traces(fig, sub, row=None, legend=False):
    fig.add_trace(go.Scatter(x=sub["timestamp"], y=sub["value_raw"], mode="lines", connectgaps=True,
                              line=dict(color=REFERENCE_LINE_COLOR), showlegend=False), row=row, col=1)
    fig.add_trace(go.Scatter(x=sub["timestamp"], y=sub["value_clean"], mode="lines", line_shape="spline",
                              line=dict(color=REFERENCE_LINE_COLOR), showlegend=False), row=row, col=2)
    for status, color in COLORS.items():
        if status == "outlier":
            continue
        m = sub["fill_method"] == status
        if m.any():
            fig.add_trace(go.Scatter(x=sub.loc[m, "timestamp"], y=sub.loc[m, "value_clean"],
                                      mode="markers", marker=dict(color=color, size=6, line=dict(width=0.5, color="white")),
                                      name=status, legendgroup=status, showlegend=legend), row=row, col=2)
    m = sub["is_outlier"]
    if m.any():
        fig.add_trace(go.Scatter(x=sub.loc[m, "timestamp"], y=sub.loc[m, "value_raw"],
                                  mode="markers", marker=dict(color=COLORS["outlier"], size=8, symbol="x"),
                                  name="outlier (raw)", legendgroup="outlier (raw)", showlegend=legend), row=row, col=1)


def render(r: dict, sensors: SensorMeta) -> None:
    fullscreen = is_fullscreen(_SECTION)
    prod = r["production"]

    if not fullscreen:
        st.subheader("Gap filling", divider="gray")
        st.caption("Parameters in the sidebar.")

        st.markdown(
            "Charts reuse the same color coding for how each point was handled:\n\n"
            "- **observed** (green) - a real, untouched reading\n"
            "- **interpolated** (yellow) - a short gap, filled by straight-line interpolation\n"
            "- **outlier_donor_regression** (purple) - an outlier, imputed straight from the most correlated sensor\n"
            "- **donor-filled** (orange) - a longer gap, filled by regression against the most similar sensor\n"
            "- **manual_validated** (teal) - reviewed and committed on the **Outliers** step\n"
            "- **outlier** (blue) - flagged as a fault and excluded from the cleaned series\n"
            "- **unfilled** (red) - gap too long and no correlated-enough sensor available, left empty"
        )

        counts = prod.groupby(["sensor_id", "fill_method"]).size().unstack(fill_value=0)
        st.dataframe(counts, width='stretch')

    # only sensors this stage actually touched (an outlier removed and/or a gap
    # filled) get a before/after row - a fully-clean sensor has before == after,
    # so a comparison chart would just be two identical lines
    changed_ids = [s for s in sensors.ids if (prod.loc[prod["sensor_id"] == s, "fill_method"] != "observed").any()]
    unchanged_ids = [s for s in sensors.ids if s not in changed_ids]

    st.write("**Before / after - raw vs. cleaned, sensors with at least one change**")
    if changed_ids:
        fig = facet_grid_before_after([sensors.label[s] for s in changed_ids])
        for i, s in enumerate(changed_ids, start=1):
            sub = decimate(prod[prod["sensor_id"] == s].sort_values("timestamp"))
            _add_sensor_traces(fig, sub, row=i, legend=(i == 1))
        fig.update_layout(height=230 * len(changed_ids), margin=dict(t=90),
                           legend=HORIZONTAL_LEGEND)
        plot(fig)
    else:
        st.success("No sensor was changed by outlier removal or gap filling.")
    if unchanged_ids:
        st.caption(f"{len(unchanged_ids)} unchanged sensor(s) hidden above: "
                   f"{', '.join(sensors.label[s] for s in unchanged_ids)}.")
