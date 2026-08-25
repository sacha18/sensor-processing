"""Downstream visual QA of the finished production dataset (soil moisture +
temperature by physical depth, group means over individual sensors, daily
aggregates, distribution by group). Reached from its own standalone page
(ui.tms.analysis_page), not a pipeline step - operates on the already-
cleaned `production` table alone, nothing here feeds back into the
pipeline."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import pipeline.tms as TMS
from ui.charts import decimate_groups, facet_grid, plot
from ui.generic.data_source import SensorMeta
from ui.format import render_capped_dataframe, to_csv_bytes, to_csv_bytes_cached, to_xlsx_bytes_cached
from ui.theme import CATEGORICAL_COLORS, HORIZONTAL_LEGEND, REFERENCE_LINE_COLOR, _rgba

# Free-form exploration section (render's "3.") - metric label -> production
# column, group-by label -> production column, resolution label -> pandas
# offset alias (None = no aggregation, one row per raw reading).
_EXPLORE_METRICS = {
    "Soil moisture (VWC)": ("vwc_final", "VWC (m3/m3)"),
    "Signal (corrected)": ("signal_corrected_final", "Signal"),
    "T1 (raw)": ("t1_raw", "Temperature (C)"),
    "T2 (raw)": ("t2_raw", "Temperature (C)"),
    "T3 (raw)": ("t3_raw", "Temperature (C)"),
}
_EXPLORE_GROUP_COLS = {"Sensor": "sensor_id", "Treatment": "treatment", "Depth (cm)": "depth_cm", "Site": "site"}
_EXPLORE_FREQS = {"Native (no aggregation)": None, "Hourly": "h", "Daily": "D", "Weekly": "W", "Monthly": "MS"}

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


def _group_label_col(df: pd.DataFrame, group_cols: list[str]) -> pd.Series:
    """One "label" per row combining group_cols (joined with " | " when
    there's more than one) - not a bare `.astype(str)` + join: pandas can
    leave a missing value as an actual float('nan') even after astype(str),
    which breaks str.join and turns into an unhashable/inconsistent lookup
    key downstream. _label() normalizes each value (including missing) to
    a real string first."""
    labeled = df[group_cols].map(_label)
    return labeled.agg(" | ".join, axis=1) if len(group_cols) > 1 else labeled[group_cols[0]]


def _add_individual_lines(fig, df, x_col, y_col, id_cols, colors, dashes, color_col, dash_col, row=None, col=None):
    """One thin, semi-transparent line per id_cols group (e.g. one per
    sensor) - never connects two different sensors together. Layered under
    the thick group-mean lines so both the noise and the signal are visible
    at once, per the field team's own "always show individuals and the
    mean" rule.

    Decimated per group first: a full native-resolution multi-sensor,
    multi-year series can be millions of points, which Plotly has to
    serialize whole into the message sent to the browser - the group-mean
    lines (thick, on top) carry the actual signal, these are just visual
    noise/context underneath, so thinning them out loses nothing that
    matters."""
    df = decimate_groups(df, id_cols)
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
    confidence than its sample size supports.

    Decimated per group first (see _add_individual_lines) - when no real
    grouping dimension is configured, color_col/dash_col fall back to
    sensor_id (_pick_color_dash_cols), so a "group" can be just one sensor:
    without this, that common case's "mean" line is silently the whole
    native-resolution series again, just as large as the backdrop it sits
    on top of."""
    df = decimate_groups(df, [color_col, dash_col])
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
        # decimated per sensor - see _add_individual_lines; these thin
        # backdrop lines don't need every native-resolution point, and a
        # full multi-year/multi-sensor series here can be huge to serialize.
        for sensor_id, g in decimate_groups(zsub, ["sensor_id"]).groupby("sensor_id"):
            color = colors.get(g[color_col].iloc[0], REFERENCE_LINE_COLOR)
            fig.add_trace(go.Scatter(
                x=g["timestamp"], y=g["temperature"], mode="lines", connectgaps=False,
                line=dict(color=_rgba(color, 0.28), width=1), showlegend=False, hoverinfo="skip",
            ), row=i, col=1)
        # same reasoning as _add_group_lines: color_col can fall back to
        # sensor_id, making a "group" mean just one sensor's full series.
        gm = decimate_groups(TMS.group_mean(zsub, "temperature", [color_col]), [color_col])
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


@st.fragment
def _render_exploration(sub: pd.DataFrame) -> None:
    """Isolated as a fragment - without it, changing Metric/Group by/
    Resolution triggers a full-page rerun (recomputing every other chart on
    this step), since Streamlit reruns the whole script on any widget
    interaction by default. A fragment reruns just this function."""
    st.write("**3. Free-form exploration**")
    st.caption("Pick a metric, group by any combination of dimensions, and choose a time resolution - chart, "
               "table and export below update accordingly.")
    col_metric, col_group, col_freq = st.columns([2, 3, 2])
    with col_metric:
        metric_label = st.selectbox("Metric", list(_EXPLORE_METRICS), key="tms_explore_metric")
    with col_group:
        group_labels = st.multiselect("Group by", list(_EXPLORE_GROUP_COLS), default=["Sensor"],
                                       key="tms_explore_group")
    with col_freq:
        freq_label = st.selectbox("Resolution", list(_EXPLORE_FREQS), index=2, key="tms_explore_freq")

    value_col, y_title = _EXPLORE_METRICS[metric_label]
    group_cols = [_EXPLORE_GROUP_COLS[g] for g in group_labels] or ["sensor_id"]
    freq = _EXPLORE_FREQS[freq_label]
    explore_df = sub.dropna(subset=[value_col])

    if explore_df.empty:
        st.info(f"No valid {metric_label} in this period.")
        return

    if freq is None:
        agg = explore_df[group_cols + ["timestamp", value_col]].rename(columns={value_col: "mean"}).copy()
        agg["n"] = 1
    else:
        agg = TMS.resample_stats(explore_df, value_col, group_cols, freq)
        if "sensor_id" not in group_cols:
            n_sensors = (explore_df.groupby(group_cols + [pd.Grouper(key="timestamp", freq=freq)], dropna=False)
                         ["sensor_id"].nunique().reset_index(name="n_sensors"))
            agg = agg.merge(n_sensors, on=group_cols + ["timestamp"])

    group_label_col = _group_label_col(agg, group_cols)
    colors = _color_map(group_label_col)
    # Native resolution can be millions of rows - decimated for the chart
    # only (Plotly has to serialize every point into the browser message);
    # the table/CSV/XLSX export below still uses the full, undecimated agg.
    plot_df = decimate_groups(agg, group_cols) if freq is None else agg
    plot_group_label_col = _group_label_col(plot_df, group_cols)
    fig = go.Figure()
    for gval in sorted(group_label_col.unique()):
        gsub = plot_df[plot_group_label_col == gval].sort_values("timestamp")
        hovertemplate = f"{gval}<br>%{{x}}<br>%{{y:.3f}}<br>n=%{{customdata}}<extra></extra>"
        fig.add_trace(go.Scatter(
            x=gsub["timestamp"], y=gsub["mean"], mode="lines", connectgaps=False,
            line=dict(color=colors[gval], width=2), name=gval,
            customdata=gsub["n"], hovertemplate=hovertemplate,
        ))
    fig.update_layout(height=420, margin=dict(t=20), legend=HORIZONTAL_LEGEND, yaxis_title=y_title)
    plot(fig)

    n_groups = group_label_col.nunique()
    st.caption(f"{int(agg['n'].sum())} valid observation(s) across {n_groups} group(s) - hover a line for "
               "its sample size (n) at each point.")
    render_capped_dataframe(agg.sort_values(group_cols + ["timestamp"]), width='stretch', height=280)
    col_csv, col_xlsx = st.columns(2)
    with col_csv:
        st.download_button("Download CSV", to_csv_bytes_cached(agg, index=False),
                            file_name="tms_exploration.csv", mime="text/csv", icon=":material/download:")
    with col_xlsx:
        st.download_button("Download XLSX", to_xlsx_bytes_cached(agg),
                            file_name="tms_exploration.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            icon=":material/download:")


def render(production: pd.DataFrame, sensors: SensorMeta) -> None:
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
    _render_exploration(sub)

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
