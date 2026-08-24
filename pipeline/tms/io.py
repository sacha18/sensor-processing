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
import logging
from pathlib import Path

import pandas as pd

from .config import FILENAME_RE, MERGED_EXPORT_COLUMNS, RAW_FIELDS, SAMPLE_DATA_DIR, TIMESTAMP_FORMATS

logger = logging.getLogger(__name__)

# Uploads are parsed in chunks of this size rather than all at once, so a
# multi-hundred-file session (a) reports progress through the logs and (b) a
# single bad/truncated file doesn't take down the whole batch - see
# load_tms_raw_from_uploads.
UPLOAD_BATCH_SIZE = 50


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


def _parse_timestamps(raw: pd.Series, name: str) -> pd.Series:
    """Tries each known TOMST export timestamp format (they vary by the
    logger's regional settings) row by row - a single file can mix formats,
    e.g. when it's been resaved in Excel and midnight rows lose their
    00:00:00 suffix while the rest keep full date+time."""
    ts = pd.to_datetime(raw, format=TIMESTAMP_FORMATS[0], errors="coerce")
    for fmt in TIMESTAMP_FORMATS[1:]:
        if ts.isna().any():
            ts = ts.fillna(pd.to_datetime(raw, format=fmt, errors="coerce"))
    if ts.isna().any():
        bad = raw[ts.isna()].iloc[0]
        raise ValueError(f"'{name}': unrecognized timestamp format, e.g. {bad!r}")
    return ts


def _parse_decimal(raw: pd.Series) -> pd.Series:
    """Some TOMST export variants use a comma decimal separator (e.g.
    '24,6875') instead of a dot - normalized before the float conversion."""
    return raw.str.replace(",", ".", regex=False).astype(float)


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
        "timestamp": _parse_timestamps(raw["timestamp_raw"], name),
        "v3_raw": _parse_decimal(raw["v3_raw"]),
        "t1_raw": _parse_decimal(raw["t1_raw"]),
        "t2_raw": _parse_decimal(raw["t2_raw"]),
        "t3_raw": _parse_decimal(raw["t3_raw"]),
        "signal_raw": _parse_decimal(raw["signal_raw"]),
        "shake": _parse_decimal(raw["shake"]),
        "err_flag": _parse_decimal(raw["err_flag"]),
        "v10_raw": raw["v10_raw"],
    })


def looks_like_merged_export(content: bytes | str) -> bool:
    """Sniffs whether an upload is this app's own "Download merged raw
    archive CSV" export (comma-separated, header row) rather than a raw
    TOMST export - lets a large multi-file session be resumed from that
    archive instead of re-uploading every raw file again."""
    text = content.decode("utf-8", errors="ignore") if isinstance(content, bytes) else content
    first_line = text.splitlines()[0] if text else ""
    cols = [c.strip() for c in first_line.split(",")]
    return cols == MERGED_EXPORT_COLUMNS


def parse_merged_export(content: bytes | str) -> pd.DataFrame:
    """Reads back this app's merged raw archive export - same schema as
    parse_tms_records's output (raw_wide), so it slots into _stack_frames
    and the rest of the pipeline (including merge_and_dedupe, which is a
    no-op on an already-deduped archive) unchanged."""
    buf = io.BytesIO(content) if isinstance(content, bytes) else io.StringIO(content)
    df = pd.read_csv(buf, dtype={"sensor_id": str, "source_file": str, "v10_raw": str})
    df["row_index"] = df["row_index"].astype(int)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    for c in ["v3_raw", "t1_raw", "t2_raw", "t3_raw", "signal_raw", "shake", "err_flag"]:
        df[c] = df[c].astype(float)
    return df[MERGED_EXPORT_COLUMNS]


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


def load_tms_raw_from_uploads(uploaded_files: list, batch_size: int = UPLOAD_BATCH_SIZE
                               ) -> tuple[pd.DataFrame, list[tuple[str, str]]]:
    """Load from a list of file-like objects (e.g. Streamlit's UploadedFile) -
    same schema as load_tms_raw. Each file is parsed either as a raw TOMST
    export or, if it's a previously downloaded merged raw archive, read back
    directly - the two can be mixed in one upload (e.g. an old archive plus
    newly downloaded raw files).

    Parsed in batches of `batch_size` so a large upload (hundreds of files)
    shows progress in the logs, and one file that failed to arrive intact or
    doesn't parse is reported and skipped rather than aborting the whole
    session - returns (raw_wide, failures), with failures as
    [(filename, error message), ...] for any file that didn't parse."""
    total = len(uploaded_files)
    frames = []
    failures = []
    logger.info("TMS upload: parsing %d file(s) in batches of %d", total, batch_size)
    for batch_start in range(0, total, batch_size):
        batch = uploaded_files[batch_start:batch_start + batch_size]
        batch_end = batch_start + len(batch)
        logger.info("TMS upload: batch %d-%d of %d", batch_start + 1, batch_end, total)
        for f in batch:
            name = getattr(f, "name", "")
            try:
                content = f.getvalue() if hasattr(f, "getvalue") else f.read()
                if looks_like_merged_export(content):
                    frames.append(parse_merged_export(content))
                else:
                    frames.append(parse_tms_records(name, content))
            except Exception as e:
                logger.warning("TMS upload: failed to parse %r: %s", name, e)
                failures.append((name, str(e)))
    logger.info("TMS upload: %d/%d file(s) parsed successfully, %d failed",
                len(frames), total, len(failures))
    if not frames:
        raise ValueError(f"No TMS files could be parsed ({len(failures)} failed)")
    return _stack_frames(frames), failures
