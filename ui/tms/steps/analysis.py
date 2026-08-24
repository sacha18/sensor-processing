"""Step 7: Analysis - downstream visual QA of the finished production
dataset (soil moisture + temperature by physical depth, group means over
individual sensors, daily aggregates, distribution by group). Nothing here
feeds back into the pipeline - it's read-only reporting on top of the
already-cleaned `production` table."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import pipeline.tms as TMS
from ui.charts import facet_grid, plot
from ui.generic.data_source import SensorMeta
from ui.format import to_csv_bytes
from ui.theme import CATEGORICAL_COLORS, HORIZONTAL_LEGEND, REFERENCE_LINE_COLOR, _rgba

_DASH_STYLES = ["solid", "dot", "dash", "dashdot", "longdash", "longdashdot"]
_UNIT_COLS = {"depth_cm", "z_cm"}
# constant stand-in for "no second grouping dimension" - lets a chart fall
# back to plain per-sensor coloring (always distinct) through the same
# groupby(color_col, dash_col) machinery as the treatment/depth case,
# instead of a separate code path.
_SINGLE_COL = "_single"


def _unit_for(col: str) -> str:
    return "cm" if col in _UNIT_COLS else ""


def _with_single(df: pd.DataFrame) -> pd.DataFrame:
    return df if _SINGLE_COL in df.columns else df.assign(**{_SINGLE_COL: ""})


def _pick_color_dash_cols(df: pd.DataFrame, primary: str, secondary: str) -> tuple[str, str]:
    """Prefer coloring by whichever of primary/secondary actually varies in
    df - treatment is the intended primary grouping, but it's an optional
    metadata field left blank by default (see ui/tms/steps/metadata.py's
    auto-seed), so a dataset with only depth/z configured would otherwise
    collapse every line to the same default grey with depth as the only
    (subtle, dash-only) cue. Falls back to depth/z as the color driver
    whenever treatment doesn't distinguish anything, and all the way to
    sensor_id (always distinct) when neither metadata field is configured -
    a chart should never render as a single "(unset)" grey line when there's
    real per-sensor signal to show."""
    if df[primary].dropna().nunique() > 1:
        return primary, secondary
    if df[secondary].dropna().nunique() > 1:
        return secondary, primary
    return "sensor_id", _SINGLE_COL


def _pick_single_grouping(df: pd.DataFrame, primary: str) -> str:
    """Same fallback idea as _pick_color_dash_cols, for a chart that only
    has one visual grouping slot available (e.g. color within an
    already-faceted row) - primary if it varies, else sensor_id."""
    return primary if df[primary].dropna().nunique() > 1 else "sensor_id"


def _colors_for(df: pd.DataFrame, color_col: str, sensors: SensorMeta) -> dict:
    """sensor_id needs the app's own per-sensor palette (ui/tms/data_source.py)
    for visual consistency with every other sensor-colored chart in this
    step, rather than a fresh categorical assignment that could disagree
    with it."""
    return sensors.color if color_col == "sensor_id" else _color_map(df[color_col])


def _color_map(values) -> dict:
    keys = sorted({v if pd.notna(v) and v != "" else None for v in values}, key=lambda v: (v is None, v))
    return {k: CATEGORICAL_COLORS[i % len(CATEGORICAL_COLORS)] for i, k in enumerate(keys)}


def _dash_map(values) -> dict:
    keys = sorted({v if pd.notna(v) else None for v in values}, key=lambda v: (v is None, v))
    return {k: _DASH_STYLES[i % len(_DASH_STYLES)] for i, k in enumerate(keys)}


def _label(v, unit: str = "") -> str:
    return "(unset)" if v is None or (isinstance(v, float) and pd.isna(v)) else f"{v}{unit}"


def _add_individual_lines(fig, df, x_col, y_col, id_cols, colors, dashes, color_col, dash_col, row=None, col=None):
    """One thin, semi-transparent line per id_cols group (e.g. one per
    sensor) - never connects two different sensors together. Layered under
    the thick group-mean lines so both the noise and the signal are visible
    at once, per the field team's own "always show individuals and the
    mean" rule."""
    for keys, sub in df.groupby(id_cols, dropna=False):
        keys = keys if isinstance(keys, tuple) else (keys,)
        by_col = dict(zip(id_cols, keys))
        color = colors.get(by_col[color_col], REFERENCE_LINE_COLOR)
        dash = dashes.get(by_col[dash_col], "solid")
        fig.add_trace(go.Scatter(
            x=sub[x_col], y=sub[y_col], mode="lines", connectgaps=False,
            line=dict(color=_rgba(color, 0.28), dash=dash, width=1),
            showlegend=False, hoverinfo="skip",
        ), row=row, col=col)


def _add_group_lines(fig, df, x_col, y_col, colors, dashes, color_col, dash_col, seen_legend,
                      row=None, col=None, n_col: str | None = None):
    """One thick line per (color_col, dash_col) group - the group mean
    layered over _add_individual_lines's per-sensor backdrop. Hover shows n
    (how many sensors/readings contributed) so a mean isn't read with more
    confidence than its sample size supports."""
    color_unit, dash_unit = _unit_for(color_col), _unit_for(dash_col)
    # dash_col == _SINGLE_COL means there's no real second dimension (the
    # sensor_id color fallback) - drop the " - " suffix instead of labeling
    # every line "<sensor> - " for a dash value that never varies.
    has_dash = dash_col != _SINGLE_COL
    for (cval, dval), sub in df.groupby([color_col, dash_col], dropna=False):
        color = colors.get(cval, REFERENCE_LINE_COLOR)
        dash = dashes.get(dval, "solid")
        legend_key = (cval, dval)
        label = _label(cval, color_unit)
        if has_dash:
            label += f" - {_label(dval, dash_unit)}"
        hovertemplate = f"{label}<br>%{{x}}<br>%{{y:.3f}}"
        customdata = None
        if n_col is not None:
            hovertemplate += "<br>n=%{customdata}"
            customdata = sub[n_col]
        hovertemplate += "<extra></extra>"
        fig.add_trace(go.Scatter(
            x=sub[x_col], y=sub[y_col], mode="lines", connectgaps=False,
            line=dict(color=color, dash=dash, width=2.5),
            name=label, legendgroup=str(legend_key), showlegend=legend_key not in seen_legend,
            customdata=customdata, hovertemplate=hovertemplate,
        ), row=row, col=col)
        seen_legend.add(legend_key)


def _period_options(production: pd.DataFrame) -> dict:
    ts = pd.to_datetime(production["timestamp"])
    options = {"Full range": (None, None)}
    if ts.empty:
        return options
    for y in sorted(ts.dt.year.unique()):
        options[f"{y} (full year)"] = (pd.Timestamp(y, 1, 1), pd.Timestamp(y, 12, 31, 23, 59, 59))
        options[f"{y} growing season (Apr 1 - Oct 31)"] = (pd.Timestamp(y, 4, 1), pd.Timestamp(y, 10, 31, 23, 59, 59))
    return options


def _filter_period(df: pd.DataFrame, window) -> pd.DataFrame:
    start, end = window
    if start is None:
        return df
    ts = pd.to_datetime(df["timestamp"])
    return df[(ts >= start) & (ts <= end)]


def _sm_chart(sub: pd.DataFrame, colors: dict, dashes: dict, color_col: str, dash_col: str, height: int = 420):
    fig = go.Figure()
    ind = sub.dropna(subset=["vwc_final"])
    # dedupe: color_col/dash_col can themselves be "sensor_id" (the fallback
    # in _pick_color_dash_cols) - groupby(["sensor_id", "sensor_id", ...])
    # would otherwise fail once pandas tries to turn the group keys back
    # into columns of the same name.
    id_cols = list(dict.fromkeys(["sensor_id", color_col, dash_col]))
    _add_individual_lines(fig, ind, "timestamp", "vwc_final", id_cols,
                           colors, dashes, color_col, dash_col)
    gm = TMS.group_mean(ind, "vwc_final", [color_col, dash_col])
    _add_group_lines(fig, gm, "timestamp", "mean", colors, dashes, color_col, dash_col, set(), n_col="n")
    fig.update_layout(height=height, margin=dict(t=20), legend=HORIZONTAL_LEGEND, yaxis_title="VWC (m3/m3)")
    return fig


def _temp_chart(temp_long: pd.DataFrame, colors: dict, color_col: str, height_per_row: int = 220):
    """One row per physical level (z_cm) instead of one shared axis - soil,
    surface and air have very different daily amplitude (air can swing
    20C+/day, soil barely moves), so sharing one y-axis buries the soil
    signal under the air noise. A single color dimension per row (no dash -
    z is now the row itself, not a line style)."""
    levels = sorted(temp_long["z_cm"].dropna().unique())
    labels = [f"{z:g} cm" for z in levels]
    fig = facet_grid(labels)
    seen = set()
    for i, z in enumerate(levels, start=1):
        zsub = temp_long[temp_long["z_cm"] == z]
        for sensor_id, g in zsub.groupby("sensor_id"):
            color = colors.get(g[color_col].iloc[0], REFERENCE_LINE_COLOR)
            fig.add_trace(go.Scatter(
                x=g["timestamp"], y=g["temperature"], mode="lines", connectgaps=False,
                line=dict(color=_rgba(color, 0.28), width=1), showlegend=False, hoverinfo="skip",
            ), row=i, col=1)
        gm = TMS.group_mean(zsub, "temperature", [color_col])
        for cval, gsub in gm.groupby(color_col, dropna=False):
            color = colors.get(cval, REFERENCE_LINE_COLOR)
            fig.add_trace(go.Scatter(
                x=gsub["timestamp"], y=gsub["mean"], mode="lines", connectgaps=False,
                line=dict(color=color, width=2.5), name=_label(cval),
                legendgroup=str(cval), showlegend=cval not in seen,
                customdata=gsub["n"], hovertemplate=f"{_label(cval)}<br>%{{x}}<br>%{{y:.2f}}C<br>n=%{{customdata}}<extra></extra>",
            ), row=i, col=1)
            seen.add(cval)
        fig.update_yaxes(title="Temperature (C)", row=i, col=1)
    fig.update_layout(height=height_per_row * len(levels), margin=dict(t=50), legend=HORIZONTAL_LEGEND)
    return fig


def _monthly_box_chart(sub: pd.DataFrame, sensors: SensorMeta, height: int = 460):
    """One box per (calendar month, sensor) - grouped by month on the x-axis
    (boxmode="group") so sensors sit side by side within each month: within-
    month spread and month-to-month seasonal shift are both visible at once.
    Grouped by sensor_id (always populated) rather than treatment/depth, so
    it's useful even before deployment metadata is configured.

    Plotly's default 1.5xIQR outlier rule paints a multi-week dry-down
    plateau as a solid blob of "outlier" points, indistinguishable from
    actual noise - jitter spreads them horizontally so their count/density
    is readable, and low opacity keeps a genuine cluster from reading as a
    single alarming smear."""
    ind = sub.dropna(subset=["vwc_final"]).copy()
    ind["month"] = pd.to_datetime(ind["timestamp"]).dt.strftime("%Y-%m")
    fig = go.Figure()
    for s in sensors.ids:
        g = ind[ind["sensor_id"] == s]
        if not len(g):
            continue
        fig.add_trace(go.Box(
            x=g["month"], y=g["vwc_final"], name=sensors.label[s],
            marker=dict(color=sensors.color[s], size=3, opacity=0.35),
            line=dict(color=sensors.color[s]), fillcolor=_rgba(sensors.color[s], 0.25),
            boxpoints="outliers", jitter=0.4, pointpos=0,
        ))
    fig.update_layout(height=height, margin=dict(t=20), yaxis_title="VWC (m3/m3)",
                       boxmode="group", legend=HORIZONTAL_LEGEND)
    return fig


def _monthly_bar_chart(sub: pd.DataFrame, sensors: SensorMeta, height: int = 420):
    """One bar per (calendar month, sensor) - the monthly mean VWC, error bar
    = std dev that month. Same month x sensor grouping as _monthly_box_chart
    so the two pair up: bars for a quick mean-to-mean comparison, the boxes
    above for the full distribution behind each bar."""
    ind = sub.dropna(subset=["vwc_final"]).copy()
    ind["month"] = pd.to_datetime(ind["timestamp"]).dt.strftime("%Y-%m")
    fig = go.Figure()
    for s in sensors.ids:
        g = ind[ind["sensor_id"] == s]
        if not len(g):
            continue
        stats = g.groupby("month")["vwc_final"].agg(mean="mean", std="std").reset_index()
        fig.add_trace(go.Bar(
            x=stats["month"], y=stats["mean"], name=sensors.label[s],
            marker=dict(color=sensors.color[s]),
            error_y=dict(type="data", array=stats["std"], visible=True, thickness=1, width=3),
        ))
    fig.update_layout(height=height, margin=dict(t=20), yaxis_title="Mean VWC (m3/m3)",
                       barmode="group", legend=HORIZONTAL_LEGEND)
    return fig


def render(r: dict, sensors: SensorMeta) -> None:
    production = r["production"]

    st.subheader("Analysis", divider="gray")
    st.caption("Downstream analysis of the finished production dataset - nothing here feeds back into the pipeline.")

    production = _with_single(production)
    sm_color_col, sm_dash_col = _pick_color_dash_cols(production, "treatment", "depth_cm")
    sm_colors = _colors_for(production, sm_color_col, sensors)
    sm_dashes = _dash_map(production[sm_dash_col])

    full_temp_long = _with_single(TMS.assign_temperature_levels(production))
    t_color_col, t_dash_col = _pick_color_dash_cols(full_temp_long, "treatment", "z_cm")
    t_colors = _colors_for(full_temp_long, t_color_col, sensors)
    t_dashes = _dash_map(full_temp_long[t_dash_col])

    # chart 2 facets by z-level (its own row per level), so it only needs one
    # color dimension, not the (color, dash) pair the other temp charts use.
    t2_color_col = _pick_single_grouping(full_temp_long, "treatment")
    t2_colors = _colors_for(full_temp_long, t2_color_col, sensors)

    period_options = _period_options(production)
    period_label = st.selectbox("Period", list(period_options), key="tms_analysis_period",
                                 help="Applies to the two charts below - full range, a calendar year, or a "
                                      "growing season (Apr 1 - Oct 31). In those charts, individual sensors are "
                                      "drawn thin/transparent, group averages thick on top - hover a thick line "
                                      "for its sample size (n). Colored by treatment where configured, falling "
                                      "back to depth/level (the more reliably populated field) otherwise, so "
                                      "lines never collapse to one grey.")
    sub = _filter_period(production, period_options[period_label])

    st.write("**1. Soil moisture - full series**")
    if sub["vwc_final"].notna().any():
        plot(_sm_chart(sub, sm_colors, sm_dashes, sm_color_col, sm_dash_col))
    else:
        st.info("No valid VWC in this period.")

    st.write("**2. Temperature by physical depth**")
    temp_long = TMS.assign_temperature_levels(sub)
    if len(temp_long):
        plot(_temp_chart(temp_long, t2_colors, t2_color_col))
    else:
        st.info("No valid temperature readings in this period.")

    st.divider()
    st.write("**4. Monthly soil moisture distribution by sensor**")
    if sub["vwc_final"].notna().any():
        plot(_monthly_box_chart(sub, sensors))
        st.write("**Monthly mean (bar)**")
        plot(_monthly_bar_chart(sub, sensors))
    else:
        st.info("No valid VWC in this period.")

    st.write("**5. Daily mean temperature by depth**")
    # dedupe: t_color_col/t_dash_col can themselves be "sensor_id" (the
    # fallback in _pick_color_dash_cols) - a duplicated "sensor_id" in the
    # groupby list breaks once pandas turns the group keys back into columns.
    t_group_cols = list(dict.fromkeys(["sensor_id", t_color_col, t_dash_col]))
    t_daily_sensor = TMS.daily_stats(full_temp_long, "temperature", t_group_cols)
    t_daily_group = TMS.daily_group_mean(t_daily_sensor, [t_color_col, t_dash_col])
    if t_daily_group["mean"].notna().any():
        fig = go.Figure()
        _add_individual_lines(fig, t_daily_sensor.dropna(subset=["mean"]), "date", "mean",
                               t_group_cols, t_colors, t_dashes, t_color_col, t_dash_col)
        _add_group_lines(fig, t_daily_group.dropna(subset=["mean"]), "date", "mean", t_colors, t_dashes,
                          t_color_col, t_dash_col, set(), n_col="n")
        fig.update_layout(height=420, margin=dict(t=20), legend=HORIZONTAL_LEGEND, yaxis_title="Temperature (C)")
        plot(fig)
    else:
        st.info("No valid temperature to aggregate.")

    st.write("**6. Daily temperature extremes** (max on top, min below - useful for daily amplitude and "
             "freeze episodes, when VWC becomes suspect and should be checked against T1/T2/T3 together)")
    t_daily_all = TMS.daily_stats(full_temp_long, "temperature", [t_color_col, t_dash_col])
    if t_daily_all[["max", "min"]].notna().any().any():
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, subplot_titles=["Daily max", "Daily min"],
                             vertical_spacing=0.1)
        seen = set()
        _add_group_lines(fig, t_daily_all.dropna(subset=["max"]), "date", "max", t_colors, t_dashes,
                          t_color_col, t_dash_col, seen, n_col="n", row=1, col=1)
        _add_group_lines(fig, t_daily_all.dropna(subset=["min"]), "date", "min", t_colors, t_dashes,
                          t_color_col, t_dash_col, set(), n_col="n", row=2, col=1)
        fig.update_yaxes(title="Temperature (C)", row=1, col=1)
        fig.update_yaxes(title="Temperature (C)", row=2, col=1)
        fig.update_layout(height=520, margin=dict(t=50), legend=HORIZONTAL_LEGEND)
        plot(fig)
        freezing = t_daily_all[t_daily_all["min"] < 1.0]
        if len(freezing):
            st.caption(f"{len(freezing)} group-day(s) with a minimum below 1C - possible freezing, VWC should "
                       "be checked visually for those periods (see Final QC step).")
    else:
        st.info("No valid temperature to aggregate.")

    st.write("Group daily soil-moisture table:")
    sm_group_cols = list(dict.fromkeys(["sensor_id", sm_color_col, sm_dash_col]))
    sm_daily_sensor = TMS.daily_stats(production, "vwc_final", sm_group_cols)
    sm_daily_group = TMS.daily_group_mean(sm_daily_sensor, [sm_color_col, sm_dash_col])
    st.dataframe(sm_daily_group, width='stretch', height=280)
    st.download_button("Download daily group SM CSV", to_csv_bytes(sm_daily_group, index=False),
                        file_name="tms_analysis_daily_sm.csv", mime="text/csv", icon=":material/download:")
