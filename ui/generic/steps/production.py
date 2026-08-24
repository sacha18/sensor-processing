"""Step 7: Production dataset - final series, downloads."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from ui.charts import add_area_trace, facet_grid, plot
from ui.generic.data_source import SensorMeta
from ui.format import to_csv_bytes
from ui.theme import HORIZONTAL_LEGEND


def render(r: dict, sensors: SensorMeta) -> None:
    st.subheader("Production dataset", divider="gray")
    st.write("**All sensors - final series**")
    fig = facet_grid([sensors.label[s] for s in sensors.ids])
    for i, s in enumerate(sensors.ids, start=1):
        sub = r["production_wide"][s]
        add_area_trace(fig, sub.index, sub.values, sensors.color[s], row=i, col=1)
    fig.update_layout(height=200 * len(sensors.ids), margin=dict(t=40))
    plot(fig)

    st.write("**All sensors overlaid** (each series standardized to mean 0 / std 1, to compare timing and shape despite very different scales/units)")
    wide = r["production_wide"]
    standardized = (wide - wide.mean()) / wide.std()
    fig = go.Figure()
    for s in sensors.ids:
        fig.add_trace(go.Scatter(x=standardized.index, y=standardized[s], mode="lines", line_shape="spline",
                                  line=dict(color=sensors.color[s], width=1.5), name=s))
    fig.update_layout(height=420, margin=dict(t=45), yaxis_title="standardized value (z-score)",
                       legend=HORIZONTAL_LEGEND)
    plot(fig)

    st.write("Long format (one row per sensor x timestamp, with method traceability):")
    st.dataframe(r["production"], width='stretch', height=300)

    st.write("Wide format (one column per sensor, ready for analysis):")
    st.dataframe(r["production_wide"], width='stretch', height=300)

    c1, c2 = st.columns(2)
    c1.download_button("Download (long) CSV", to_csv_bytes(r["production"].set_index("timestamp")),
                        file_name="sensors_clean_long.csv", mime="text/csv", icon=":material/download:")
    c2.download_button("Download (wide) CSV", to_csv_bytes(r["production_wide"]),
                        file_name="sensors_clean_wide.csv", mime="text/csv", icon=":material/download:")
