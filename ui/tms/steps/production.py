"""Step 7: Production dataset - final series, downloads."""
from __future__ import annotations

import streamlit as st

from ui.charts import add_area_trace, facet_grid, plot
from ui.generic.data_source import SensorMeta
from ui.format import to_csv_bytes


def render(r: dict, sensors: SensorMeta) -> None:
    production = r["production"]

    st.subheader("Production dataset", divider="gray")
    st.write("**VWC (final) - all sensors**")
    fig = facet_grid([sensors.label[s] for s in sensors.ids])
    for i, s in enumerate(sensors.ids, start=1):
        sub = production[production["sensor_id"] == s].sort_values("timestamp").dropna(subset=["vwc_final"])
        if len(sub):
            add_area_trace(fig, sub["timestamp"], sub["vwc_final"].to_numpy(), sensors.color[s], row=i, col=1)
    fig.update_layout(height=200 * len(sensors.ids), margin=dict(t=40))
    plot(fig)

    st.write("Production table (one row per sensor x timestamp):")
    st.dataframe(production, width='stretch', height=300)

    st.download_button("Download production CSV", to_csv_bytes(production.set_index("timestamp")),
                        file_name="tms_production.csv", mime="text/csv", icon=":material/download:")
