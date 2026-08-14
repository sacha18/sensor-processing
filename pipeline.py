"""Generic sensor data pipeline: load -> dedupe -> regularize -> outliers ->
similarity -> gap fill -> production dataset.

Works on any folder of `<sensor_id>.json` or `<sensor_id>.csv` files, each a
list/table of observations with `phenomenon_time` and `result` columns
(`observation_id` optional) - a CSV is just the JSON schema's fields as a
table instead of a list of dicts, same required columns either way. Sensor
count, names, ranges and native sampling rate are all discovered from the
data - none of it is hardcoded to a particular deployment.

Pure pandas/numpy/scipy logic, no UI here - app.py (Streamlit) drives it and
displays each phase.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform

STEP_MIN = 30
MAX_INTERP_GAP = 4       # steps (2h): filled by linear time-interpolation
HAMPEL_HALF_WINDOW = 5   # points each side of the tested point
HAMPEL_K = 6             # MAD multiplier -> outlier threshold
SUPPORTED_EXTENSIONS = [".json", ".csv"]

# resolution order: SENSOR_DATA_DIR env var (e.g. a mounted docker volume) ->
# bundled sample dataset, so the app always has something to show
ENV_DATA_DIR = os.environ.get("SENSOR_DATA_DIR", "data/bp")
SAMPLE_DATA_DIR = Path(__file__).parent / "sample_data"


def _has_sensor_files(d: Path) -> bool:
    return any(d.glob(f"*{ext}") for ext in SUPPORTED_EXTENSIONS)


def resolve_data_dir(preferred: str | Path | None = None) -> Path:
    candidates = [Path(preferred)] if preferred else []
    candidates += [Path(ENV_DATA_DIR), SAMPLE_DATA_DIR]
    for c in candidates:
        if c.exists() and _has_sensor_files(c):
            return c
    raise FileNotFoundError(
        f"No sensor {'/'.join(SUPPORTED_EXTENSIONS)} files found in any of: {[str(c) for c in candidates]}. "
        "Mount a dataset directory (SENSOR_DATA_DIR / docker volume at /data)."
    )


# ---- 1. load ----------------------------------------------------------------

def _parse_records(name: str, content: bytes | str):
    """Dispatch by extension: .csv -> a table with phenomenon_time/result columns,
    .json -> a list of {phenomenon_time, result, ...} dicts. Same required fields
    either way - a CSV export of the JSON schema loads identically."""
    suffix = Path(name).suffix.lower()
    if suffix == ".csv":
        buf = io.BytesIO(content) if isinstance(content, bytes) else io.StringIO(content)
        return pd.read_csv(buf)
    text = content.decode("utf-8") if isinstance(content, bytes) else content
    return json.loads(text)


def _sensor_frame(sensor_id: str, records) -> pd.DataFrame:
    df = pd.DataFrame(records)
    df["sensor_id"] = sensor_id
    df["timestamp"] = pd.to_datetime(df["phenomenon_time"], utc=True)
    df["value_raw"] = df["result"].astype(float)
    if "observation_id" not in df.columns:
        df["observation_id"] = range(len(df))
    # CSV gives int64, JSON gives str - normalize so concatenating sensors from
    # different formats doesn't produce a mixed-type column (breaks Arrow display)
    df["observation_id"] = df["observation_id"].astype(str)
    return df[["sensor_id", "observation_id", "timestamp", "value_raw"]]


def _stack_frames(frames: list) -> pd.DataFrame:
    if not frames:
        raise ValueError("No sensor files provided")
    return pd.concat(frames, ignore_index=True).sort_values(["sensor_id", "timestamp"]).reset_index(drop=True)


def load_raw(data_dir: Path = None) -> pd.DataFrame:
    """Load every `<sensor_id>.json`/`.csv` file in data_dir (falls back per resolve_data_dir)."""
    data_dir = resolve_data_dir(data_dir) if data_dir is None else Path(data_dir)
    files = sorted(f for ext in SUPPORTED_EXTENSIONS for f in data_dir.glob(f"*{ext}"))
    if not files:
        raise FileNotFoundError(f"No {'/'.join(SUPPORTED_EXTENSIONS)} files in {data_dir}")
    return _stack_frames([_sensor_frame(f.stem, _parse_records(f.name, f.read_bytes())) for f in files])


def load_raw_from_uploads(uploaded_files: list) -> pd.DataFrame:
    """Load from a list of file-like objects (e.g. Streamlit's UploadedFile, .json or
    .csv) - each file's stem becomes its sensor_id, same schema as load_raw."""
    frames = []
    for f in uploaded_files:
        name = getattr(f, "name", "sensor.json")
        sensor_id = Path(name).stem
        content = f.getvalue() if hasattr(f, "getvalue") else f.read()
        frames.append(_sensor_frame(sensor_id, _parse_records(name, content)))
    return _stack_frames(frames)


def parse_units_mapping(name: str, content: bytes | str) -> dict:
    """Optional sensor_id -> unit label mapping (display only, not used in any
    computation) - different sensor types rarely share a unit (e.g. a piezometer
    in cm vs. a scintillometer in W/m2), so labeling is opt-in rather than assumed.
    Accepts a CSV with sensor_id/unit columns, or a JSON object {"sensor_id": "unit"}."""
    suffix = Path(name).suffix.lower()
    if suffix == ".csv":
        buf = io.BytesIO(content) if isinstance(content, bytes) else io.StringIO(content)
        df = pd.read_csv(buf)
        cols = {c.strip().lower(): c for c in df.columns}
        id_col = cols.get("sensor_id", df.columns[0])
        unit_col = cols.get("unit", df.columns[1] if len(df.columns) > 1 else df.columns[0])
        return {str(k): str(v) for k, v in zip(df[id_col], df[unit_col])}
    text = content.decode("utf-8") if isinstance(content, bytes) else content
    return {str(k): str(v) for k, v in json.loads(text).items()}


# ---- 2. de-duplicate ---------------------------------------------------------
# keep the highest observation_id (most recent write) for any repeated
# sensor/timestamp pair

def dedupe(raw_long: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    dup_counts = raw_long.groupby(["sensor_id", "timestamp"]).size()
    dup_report = dup_counts[dup_counts > 1].reset_index(name="n_dup")

    out = raw_long.copy()
    out["_obs_id_num"] = out["observation_id"].astype(int)
    out = (
        out.sort_values("_obs_id_num")
        .drop_duplicates(subset=["sensor_id", "timestamp"], keep="last")
        .drop(columns="_obs_id_num")
        .sort_values(["sensor_id", "timestamp"])
        .reset_index(drop=True)
    )
    return out, dup_report


# ---- 3. regularize onto a fixed time grid ------------------------------------
# one common grid across all sensors; a sensor's own [first, last] observation
# window marks which grid points are legitimately "in range" for it (points
# outside that window are absence-of-deployment, not gaps to fill)

def regularize(raw_long: pd.DataFrame, step_min: int = STEP_MIN):
    span = raw_long.groupby("sensor_id")["timestamp"].agg(obs_start="min", obs_end="max")
    grid = pd.date_range(span["obs_start"].min(), span["obs_end"].max(), freq=f"{step_min}min")

    rows = []
    for sensor_id, row in span.iterrows():
        sub = grid[(grid >= row["obs_start"]) & (grid <= row["obs_end"])]
        rows.append(pd.DataFrame({"sensor_id": sensor_id, "timestamp": sub}))
    reg = pd.concat(rows, ignore_index=True)
    reg = reg.merge(raw_long[["sensor_id", "timestamp", "value_raw"]], on=["sensor_id", "timestamp"], how="left")
    reg = reg.sort_values(["sensor_id", "timestamp"]).reset_index(drop=True)
    return reg, span, grid


# ---- 4. outlier detection ----------------------------------------------------
# Four independent, toggleable methods catching different fault modes. Each
# contributes its own is_outlier_<method> column; is_outlier is their OR, so a
# point's flags stay individually inspectable instead of collapsing to one bit.

# a) Hampel filter: flags points far (k MADs) from the median of a symmetric
# local window. A slow multi-step ramp (real event) stays inside the window's
# spread and is not flagged; an isolated spike is.

def hampel_flags(x: pd.Series, half_window: int = HAMPEL_HALF_WINDOW, k: float = HAMPEL_K) -> pd.Series:
    vals = x.to_numpy(dtype=float)
    n = len(vals)
    flags = np.zeros(n, dtype=bool)
    for i in range(n):
        if np.isnan(vals[i]):
            continue
        lo, hi = max(0, i - half_window), min(n, i + half_window + 1)
        w = vals[lo:hi]
        w = w[~np.isnan(w)]
        if len(w) < 3:
            continue
        med = np.median(w)
        mad = np.median(np.abs(w - med)) * 1.4826
        if mad == 0:
            continue
        if abs(vals[i] - med) > k * mad:
            flags[i] = True
    return pd.Series(flags, index=x.index)


# b) Flatline / stuck-sensor detector: a run of `min_run`+ back-to-back
# *identical* readings. Hampel structurally can't catch this (MAD is 0 inside
# a flatline, so it's skipped by design) - a distinct fault mode needs a
# distinct method.

def flatline_flags(x: pd.Series, min_run: int = 6) -> pd.Series:
    vals = x.to_numpy(dtype=float)
    n = len(vals)
    flags = np.zeros(n, dtype=bool)
    i = 0
    while i < n:
        if np.isnan(vals[i]):
            i += 1
            continue
        j = i + 1
        while j < n and vals[j] == vals[i]:
            j += 1
        if j - i >= min_run:
            flags[i:j] = True
        i = j
    return pd.Series(flags, index=x.index)


# c) Percentile / extreme-value clipping: flags readings outside this sensor's
# own [lo_pct, hi_pct] percentile range - a blunt, context-free sanity bound
# (e.g. a sign flip or a decimal-point glitch that a local window won't catch
# because the bad value doesn't look "sudden" relative to its own tiny run).

def percentile_flags(x: pd.Series, lo_pct: float = 0.5, hi_pct: float = 99.5) -> pd.Series:
    vals = x.to_numpy(dtype=float)
    finite = vals[~np.isnan(vals)]
    if len(finite) < 10:
        return pd.Series(np.zeros(len(vals), dtype=bool), index=x.index)
    lo, hi = np.percentile(finite, [lo_pct, hi_pct])
    flags = np.where(np.isnan(vals), False, (vals < lo) | (vals > hi))
    return pd.Series(flags, index=x.index)


# d) Rate-of-change filter: flags a step whose |delta| exceeds k times this
# sensor's own typical (median) step size. Self-calibrating per sensor, but
# unlike Hampel it has no window context, so a genuine sharp ramp (several
# large steps in the same direction) gets flagged too - off by default, opt-in
# for datasets known not to have legitimate rapid swings.

def rate_flags(x: pd.Series, k: float = 8.0) -> pd.Series:
    vals = x.to_numpy(dtype=float)
    n = len(vals)
    flags = np.zeros(n, dtype=bool)
    diffs = np.abs(np.diff(vals))
    finite = diffs[~np.isnan(diffs)]
    if len(finite) < 5:
        return pd.Series(flags, index=x.index)
    scale = np.median(finite)
    if scale == 0:
        scale = np.mean(finite)  # many exact-repeat steps (low-res sensor): median collapses to 0
    if scale == 0:
        return pd.Series(flags, index=x.index)
    thresh = k * scale
    for i in range(1, n):
        if np.isnan(vals[i]) or np.isnan(vals[i - 1]):
            continue
        if abs(vals[i] - vals[i - 1]) > thresh:
            flags[i] = True
    return pd.Series(flags, index=x.index)


DEFAULT_OUTLIER_CFG = {
    "use_hampel": True, "hampel_half_window": HAMPEL_HALF_WINDOW, "hampel_k": HAMPEL_K,
    "use_flatline": True, "flatline_min_run": 6,
    "use_percentile": False, "pct_low": 0.5, "pct_high": 99.5,
    "use_rate": False, "rate_k": 8.0,
}


def detect_outliers(reg_long: pd.DataFrame, outlier_cfg: dict = None) -> pd.DataFrame:
    cfg = {**DEFAULT_OUTLIER_CFG, **(outlier_cfg or {})}
    out = reg_long.copy()
    g = out.groupby("sensor_id")["value_raw"]

    out["is_outlier_hampel"] = g.transform(lambda s: hampel_flags(s, cfg["hampel_half_window"], cfg["hampel_k"])) if cfg["use_hampel"] else False
    out["is_outlier_flatline"] = g.transform(lambda s: flatline_flags(s, cfg["flatline_min_run"])) if cfg["use_flatline"] else False
    out["is_outlier_range"] = g.transform(lambda s: percentile_flags(s, cfg["pct_low"], cfg["pct_high"])) if cfg["use_percentile"] else False
    out["is_outlier_rate"] = g.transform(lambda s: rate_flags(s, cfg["rate_k"])) if cfg["use_rate"] else False

    method_cols = ["is_outlier_hampel", "is_outlier_flatline", "is_outlier_range", "is_outlier_rate"]
    out["is_outlier"] = out[method_cols].any(axis=1)
    out["value_qc"] = out["value_raw"].where(~out["is_outlier"])
    return out


# ---- 5. similarity between sensors -------------------------------------------
# correlation on levels (overall behaviour) and on first differences (do
# sensors move together, event by event?) -> used to pick a gap-fill donor

def similarity(reg_long: pd.DataFrame) -> dict:
    wide_qc = reg_long.pivot(index="timestamp", columns="sensor_id", values="value_qc").sort_index()
    cor_level = wide_qc.corr()
    cor_diff = wide_qc.diff().corr()

    dist = 1 - cor_level.abs()
    dist_vals = np.array(dist.values, copy=True)
    np.fill_diagonal(dist_vals, 0.0)
    # linkage/squareform need >=2 observations - a single-sensor dataset has no
    # pairwise distances to cluster, so there's nothing to compute
    Z = linkage(squareform(dist_vals, checks=False), method="average") if len(dist_vals) >= 2 else None

    donor_of = {}
    for s in cor_level.columns:
        cc = cor_level[s].drop(index=s)
        donor_of[s] = cc.idxmax() if cc.notna().any() else None

    return {"wide_qc": wide_qc, "cor_level": cor_level, "cor_diff": cor_diff, "linkage": Z, "donor_of": donor_of, "labels": list(cor_level.columns)}


# ---- 6. gap filling -----------------------------------------------------------
# a) short in-range gaps  -> linear time-interpolation
# b) longer in-range gaps -> linear regression on the most similar donor sensor
# c) anything left        -> NaN, flagged unfilled

def interp_short_gaps(x: pd.Series, max_gap: int = MAX_INTERP_GAP):
    vals = x.to_numpy(dtype=float).copy()
    n = len(vals)
    method = np.array([None] * n, dtype=object)
    is_na = np.isnan(vals)

    i = 0
    while i < n:
        if not is_na[i]:
            i += 1
            continue
        j = i
        while j < n and is_na[j]:
            j += 1
        gap_len = j - i
        if i == 0 or j == n:
            method[i:j] = "edge_unfilled"
        elif gap_len <= max_gap:
            x0, x1 = vals[i - 1], vals[j]
            vals[i:j] = np.interp(np.arange(1, gap_len + 1), [0, gap_len + 1], [x0, x1])
            method[i:j] = "linear_interp"
        i = j
    return pd.Series(vals, index=x.index), pd.Series(method, index=x.index)


def donor_fill(target: pd.Series, donor: pd.Series, method: pd.Series):
    target = target.copy()
    method = method.copy()
    need = target.isna() & method.isna()
    if not need.any() or donor.isna().all():
        return target, method
    ok = target.notna() & donor.notna()
    if ok.sum() >= 5:
        a, b = np.polyfit(donor[ok], target[ok], 1)
        can_predict = need & donor.notna()
        target.loc[can_predict] = a * donor.loc[can_predict] + b
        method.loc[can_predict] = "donor_regression"
    method.loc[target.isna() & method.isna()] = "unfilled"
    return target, method


def gap_fill(reg_long: pd.DataFrame, sim: dict, max_gap: int = MAX_INTERP_GAP):
    wide_qc = sim["wide_qc"]

    stage1_vals, stage1_method = {}, {}
    for s in wide_qc.columns:
        v, m = interp_short_gaps(wide_qc[s], max_gap)
        stage1_vals[s], stage1_method[s] = v, m
    stage1 = pd.DataFrame(stage1_vals)
    method1 = pd.DataFrame(stage1_method)

    stage2 = stage1.copy()
    method2 = method1.copy()
    for s in stage1.columns:
        donor = sim["donor_of"].get(s)
        if donor is None:
            still_na = stage2[s].isna() & method2[s].isna()
            method2.loc[still_na, s] = "unfilled"
            continue
        v, m = donor_fill(stage1[s], stage1[donor], method1[s])
        stage2[s] = v
        method2[s] = m

    value_clean_long = stage2.reset_index().melt(id_vars="timestamp", var_name="sensor_id", value_name="value_clean")
    method_long = method2.reset_index().melt(id_vars="timestamp", var_name="sensor_id", value_name="fill_method")

    production = reg_long.merge(value_clean_long, on=["sensor_id", "timestamp"], how="left")
    production = production.merge(method_long, on=["sensor_id", "timestamp"], how="left")
    observed_mask = production["fill_method"].isna() & production["value_raw"].notna() & ~production["is_outlier"]
    production.loc[observed_mask, "fill_method"] = "observed"
    production["fill_method"] = production["fill_method"].fillna("unfilled")
    return production.sort_values(["sensor_id", "timestamp"]).reset_index(drop=True), stage1, method1


# ---- 7. post-processing: aggregation & smoothing -------------------------------
# both operate on the cleaned+gap-filled value_clean series, downstream of QC -
# neither feeds back into it, so the raw-resolution production series stays intact

AGG_FREQ = "1D"
SMOOTH_WINDOW = 5    # steps, centered
SMOOTH_METHOD = "mean"  # "mean" or "median"


def aggregate(production: pd.DataFrame, freq: str = AGG_FREQ) -> pd.DataFrame:
    """Per-sensor summary stats (mean/min/max/std/count) over a coarser time bucket
    (e.g. daily), one row per (period, sensor)."""
    agg = (
        production.set_index("timestamp")
        .groupby(["sensor_id", pd.Grouper(freq=freq)])["value_clean"]
        .agg(["mean", "min", "max", "std", "count"])
        .reset_index()
        .rename(columns={"timestamp": "period"})
        .sort_values(["sensor_id", "period"])
        .reset_index(drop=True)
    )
    return agg


def smooth(production_wide: pd.DataFrame, window: int = SMOOTH_WINDOW, method: str = SMOOTH_METHOD) -> pd.DataFrame:
    """Rolling mean/median over the cleaned wide series - a trend/display aid
    layered on top of value_clean, not a replacement for it."""
    roll = production_wide.rolling(window=window, center=True, min_periods=1)
    return roll.median() if method == "median" else roll.mean()


# ---- orchestration ------------------------------------------------------------

def process_pipeline(raw_long: pd.DataFrame, step_min: int = STEP_MIN,
                      outlier_cfg: dict = None, max_interp_gap: int = MAX_INTERP_GAP,
                      agg_freq: str = AGG_FREQ, smooth_window: int = SMOOTH_WINDOW,
                      smooth_method: str = SMOOTH_METHOD) -> dict:
    """Run dedupe -> ... -> production -> aggregation/smoothing on an already-loaded
    raw_long frame (from load_raw or load_raw_from_uploads)."""
    deduped, dup_report = dedupe(raw_long)
    reg_long, span, grid = regularize(deduped, step_min)
    qc_long = detect_outliers(reg_long, outlier_cfg)
    sim = similarity(qc_long)
    production, stage1, method1 = gap_fill(qc_long, sim, max_interp_gap)
    production_wide = production.pivot(index="timestamp", columns="sensor_id", values="value_clean").sort_index()
    agg = aggregate(production, agg_freq)
    smoothed_wide = smooth(production_wide, smooth_window, smooth_method)

    return {
        "raw_long": raw_long,
        "deduped": deduped,
        "dup_report": dup_report,
        "reg_long": reg_long,
        "span": span,
        "grid": grid,
        "qc_long": qc_long,
        "sim": sim,
        "production": production,
        "production_wide": production_wide,
        "agg": agg,
        "smoothed_wide": smoothed_wide,
    }


def run_pipeline(data_dir: Path = None, step_min: int = STEP_MIN,
                  outlier_cfg: dict = None, max_interp_gap: int = MAX_INTERP_GAP) -> dict:
    """Convenience wrapper: load_raw(data_dir) then process_pipeline(...)."""
    raw_long = load_raw(data_dir)
    return process_pipeline(raw_long, step_min, outlier_cfg, max_interp_gap)
