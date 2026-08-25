"""Step 7 (last): Production dataset - final series, download. Analysis
lives on its own page now (ui.tms.analysis_page), reached from the
"Analyze" button here rather than being a step in this stepper."""
from __future__ import annotations

import streamlit as st

from ui.charts import add_area_trace, facet_grid, plot
from ui.generic.data_source import SensorMeta
from ui.format import to_csv_bytes_cached
from ui.stepper import fixed_bottom_right


def _render_bottom_bar(production, analysis_page) -> None:
    """Analyze (secondary) just to the left of Download (primary) - this is
    the last step, so the stepper's own Next never renders here."""
    with fixed_bottom_right("production_next_bar"):
        if st.button("Analyze", key="production_analyze", width="content"):
            st.switch_page(analysis_page)
        st.download_button(
            "Download", to_csv_bytes_cached(production.set_index("timestamp")),
            file_name="tms_production.csv", mime="text/csv", type="primary",
            key="production_download", width="content",
        )


def render(r: dict, sensors: SensorMeta, analysis_page) -> None:
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

    _render_bottom_bar(production, analysis_page)
