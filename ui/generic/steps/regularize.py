"""Step 3: Regularization - common time grid overview."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from ui.charts import decimate, plot
from ui.generic.data_source import SensorMeta
from ui.theme import COLORS, HORIZONTAL_LEGEND


def render(r: dict, step_min: int, sensors: SensorMeta) -> None:
    st.subheader("Regular time grid", divider="gray")
    st.write(f"Common grid at **{step_min} min** steps, from `{r['grid'].min()}` to `{r['grid'].max()}` ({len(r['grid'])} slots).")
    st.dataframe(r["span"].reset_index(), width='stretch')

    reg = r["reg_long"]
    miss = reg.groupby("sensor_id").agg(
        slots=("value_raw", "size"),
        missing=("value_raw", lambda s: s.isna().sum()),
    ).reset_index()
    miss["% missing"] = (100 * miss["missing"] / miss["slots"]).round(1)
    st.dataframe(miss, width='stretch')
    st.caption("A slot only counts as \"missing\" if it falls within that sensor's own deployment window (no fabricated data outside its measurement period).")

    st.write("**Grid coverage per sensor**")
    st.caption("Green = a raw reading snapped onto the grid, red = snapping left a gap to fill later, blank = "
               "outside that sensor's deployment window (not a gap).")
    fig = go.Figure()
    for i, s in enumerate(sensors.ids):
        # matches ui/tms/steps/load.py's equivalent "per-sensor timeline"
        # chart - this is just showing coverage/gaps, not exact reading
        # times, so decimate() loses nothing that matters here.
        sub = decimate(reg[reg["sensor_id"] == s])
        observed = sub[sub["value_raw"].notna()]
        missing = sub[sub["value_raw"].isna()]
        fig.add_trace(go.Scatter(x=observed["timestamp"], y=[sensors.label[s]] * len(observed), mode="markers",
                                  marker=dict(symbol="line-ns", line=dict(width=2, color=COLORS["observed"]), size=9),
                                  name="observed", legendgroup="observed", showlegend=(i == 0), hoverinfo="x"))
        fig.add_trace(go.Scatter(x=missing["timestamp"], y=[sensors.label[s]] * len(missing), mode="markers",
                                  marker=dict(symbol="line-ns", line=dict(width=2, color=COLORS["unfilled"]), size=9),
                                  name="missing (new gap)", legendgroup="missing", showlegend=(i == 0), hoverinfo="x"))
    fig.update_layout(height=70 + 36 * len(sensors.ids), margin=dict(t=30), legend=HORIZONTAL_LEGEND)
    plot(fig)
