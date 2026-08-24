"""Loading raw sensor observations and optional unit labels.

Works on any folder of `<sensor_id>.json` or `<sensor_id>.csv` files, each a
list/table of observations with `phenomenon_time` and `result` columns
(`observation_id` optional) - a CSV is just the JSON schema's fields as a
table instead of a list of dicts, same required columns either way.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd

from .config import ENV_DATA_DIR, SAMPLE_DATA_DIR, SUPPORTED_EXTENSIONS


def _has_sensor_files(d: Path) -> bool:
    return any(d.glob(f"*{ext}") for ext in SUPPORTED_EXTENSIONS)


def resolve_data_dir(preferred: str | Path | None = None) -> Path:
    candidates = [Path(preferred)] if preferred else []
    if ENV_DATA_DIR:
        candidates.append(Path(ENV_DATA_DIR))
    candidates.append(SAMPLE_DATA_DIR)
    for c in candidates:
        if c.exists() and _has_sensor_files(c):
            return c
    raise FileNotFoundError(
        f"No sensor {'/'.join(SUPPORTED_EXTENSIONS)} files found in any of: {[str(c) for c in candidates]}. "
        "Set SENSOR_DATA_DIR to a dataset directory."
    )


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
