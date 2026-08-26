"""Step 6 (last): Production dataset - final series, downloads. Analysis
lives on its own page now (ui.generic.analysis_page), reached from the
"Analyze" button here rather than being a step in this stepper."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from ui.charts import add_area_trace, decimate, facet_grid, plot
from ui.generic.data_source import SensorMeta
from ui.format import render_capped_dataframe, to_csv_bytes, to_csv_bytes_cached
from ui.stepper import fixed_bottom_right
from ui.theme import HORIZONTAL_LEGEND


def render(r: dict, sensors: SensorMeta, analysis_page) -> None:
    st.subheader("Production dataset", divider="gray")
    st.write("**All sensors - final series**")
    fig = facet_grid([sensors.label[s] for s in sensors.ids])
    for i, s in enumerate(sensors.ids, start=1):
        sub = decimate(r["production_wide"][s])
        add_area_trace(fig, sub.index, sub.values, sensors.color[s], row=i, col=1)
    fig.update_layout(height=200 * len(sensors.ids), margin=dict(t=40))
    plot(fig)

    st.write("**All sensors overlaid** (each series standardized to mean 0 / std 1, to compare timing and shape despite very different scales/units)")
    wide = r["production_wide"]
    standardized = (wide - wide.mean()) / wide.std()
    fig = go.Figure()
    for s in sensors.ids:
        sub = decimate(standardized[s])
        fig.add_trace(go.Scatter(x=sub.index, y=sub.values, mode="lines", line_shape="spline",
                                  line=dict(color=sensors.color[s], width=1.5), name=s))
    fig.update_layout(height=420, margin=dict(t=45), yaxis_title="standardized value (z-score)",
                       legend=HORIZONTAL_LEGEND)
    plot(fig)

    st.write("Long format (one row per sensor x timestamp, with method traceability):")
    render_capped_dataframe(r["production"], width='stretch', height=300)

    st.write("Wide format (one column per sensor, ready for analysis):")
    render_capped_dataframe(r["production_wide"], width='stretch', height=300)

    st.download_button("Download (wide) CSV", to_csv_bytes(r["production_wide"]),
                        file_name="sensors_clean_wide.csv", mime="text/csv", icon=":material/download:")

    with fixed_bottom_right("production_next_bar"):
        if st.button("Analyze", icon=":material/insights:", key="production_analyze", width="content"):
            st.switch_page(analysis_page)
        st.download_button(
            "Download", to_csv_bytes_cached(r["production"].set_index("timestamp")),
            file_name="sensors_clean_long.csv", mime="text/csv", type="primary",
            key="production_download", width="content",
        )
