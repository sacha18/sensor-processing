"""Loading raw TOMST TMS-4 observations.

Works on `data_<sensor serial>_<yyyy>_<mm>_<dd>_<part>.csv` files - the
standard TOMST export naming (loggers are offline; a sensor's data typically
arrives as a handful of these files from periodic manual downloads). Each
file is a semicolon-separated, headerless table of 10 fields (V1-V10:
index;DTM;v3;T1;T2;T3;Signal;Shake;ErrFlag;v10) - no unit conversion or
channel-meaning assumption happens here, just parsing; every field is
carried through untouched, including the ones unused downstream (see
config.py::RAW_FIELDS), for archive fidelity.
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from .config import FILENAME_RE, RAW_FIELDS, SAMPLE_DATA_DIR, TIMESTAMP_FORMAT


def extract_sensor_id(filename: str) -> str:
    m = FILENAME_RE.search(Path(filename).name)
    if not m:
        raise ValueError(
            f"'{filename}' doesn't match the TOMST export pattern data_<serial>_<yyyy>_<mm>_<dd>_<part>.csv"
        )
    return m.group(1)


def download_sort_key(filename: str) -> tuple:
    """(year, month, day, part) parsed from the filename - orders a sensor's
    downloads chronologically so the latest one wins an overlap in continuity.py."""
    m = FILENAME_RE.search(Path(filename).name)
    if not m:
        raise ValueError(f"'{filename}' doesn't match the TOMST export pattern")
    return tuple(int(g) for g in m.groups()[1:])


def _has_sensor_files(d: Path) -> bool:
    return any(FILENAME_RE.search(f.name) for f in d.glob("*.csv"))


def resolve_tms_data_dir(preferred: str | Path | None = None) -> Path:
    candidates = [Path(preferred)] if preferred else []
    candidates += [SAMPLE_DATA_DIR]
    for c in candidates:
        if c.exists() and _has_sensor_files(c):
            return c
    raise FileNotFoundError(
        "No TOMST TMS-4 csv files (data_<serial>_<yyyy>_<mm>_<dd>_<part>.csv) found in any of: "
        f"{[str(c) for c in candidates]}."
    )


def parse_tms_records(name: str, content: bytes | str) -> pd.DataFrame:
    """Parses one TOMST export file into a per-row DataFrame with sensor_id/
    source_file attached - the raw fields, plus a standardized `timestamp`,
    unmodified otherwise."""
    buf = io.BytesIO(content) if isinstance(content, bytes) else io.StringIO(content)
    raw = pd.read_csv(buf, sep=";", header=None, dtype=str)
    # a file with no trailing ";" (no V10) still parses fine - reindex pads the
    # missing column with NaN rather than raising, so V10 is optional not required
    raw = raw.reindex(columns=range(len(RAW_FIELDS)))
    raw.columns = RAW_FIELDS

    return pd.DataFrame({
        "sensor_id": extract_sensor_id(name),
        "source_file": Path(name).name,
        "row_index": raw["row_index"].astype(int),
        "timestamp": pd.to_datetime(raw["timestamp_raw"], format=TIMESTAMP_FORMAT),
        "v3_raw": raw["v3_raw"].astype(float),
        "t1_raw": raw["t1_raw"].astype(float),
        "t2_raw": raw["t2_raw"].astype(float),
        "t3_raw": raw["t3_raw"].astype(float),
        "signal_raw": raw["signal_raw"].astype(float),
        "shake": raw["shake"].astype(float),
        "err_flag": raw["err_flag"].astype(float),
        "v10_raw": raw["v10_raw"],
    })


def _stack_frames(frames: list) -> pd.DataFrame:
    if not frames:
        raise ValueError("No TMS files provided")
    return pd.concat(frames, ignore_index=True).sort_values(["sensor_id", "timestamp"]).reset_index(drop=True)


def load_tms_raw(data_dir: Path = None) -> pd.DataFrame:
    """Load every TOMST export file in data_dir (falls back to the bundled sample data)."""
    data_dir = resolve_tms_data_dir(data_dir) if data_dir is None else Path(data_dir)
    files = sorted((f for f in data_dir.glob("*.csv") if FILENAME_RE.search(f.name)), key=lambda f: f.name)
    if not files:
        raise FileNotFoundError(f"No TOMST TMS-4 csv files in {data_dir}")
    return _stack_frames([parse_tms_records(f.name, f.read_bytes()) for f in files])


def load_tms_raw_from_uploads(uploaded_files: list) -> pd.DataFrame:
    """Load from a list of file-like objects (e.g. Streamlit's UploadedFile) -
    same schema as load_tms_raw."""
    frames = []
    for f in uploaded_files:
        name = getattr(f, "name", "")
        content = f.getvalue() if hasattr(f, "getvalue") else f.read()
        frames.append(parse_tms_records(name, content))
    return _stack_frames(frames)
