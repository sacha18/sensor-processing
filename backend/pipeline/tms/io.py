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
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

from .. import store
from .config import FILENAME_RE, MERGED_EXPORT_COLUMNS, RAW_FIELDS, TIMESTAMP_FORMATS

logger = logging.getLogger(__name__)

# Uploads are parsed in batches of this size - reports progress and keeps
# one bad file from failing the whole session (see load_tms_raw_from_uploads).
UPLOAD_BATCH_SIZE = 50

# DuckDB TRY_STRPTIME equivalents of TIMESTAMP_FORMATS - same codes, same
# fallback order (see _parse_timestamps).
_DUCKDB_TIMESTAMP_FORMATS = TIMESTAMP_FORMATS
_RAW_CSV_COLUMNS = {c: "VARCHAR" for c in RAW_FIELDS}
# every RAW_FIELDS column except v10_raw (optional/unused, carried through
# as-is - see config.py::RAW_FIELDS) must parse cleanly for a file to be
# accepted - same "any bad value rejects the whole file" rule _parse_timestamps/
# _parse_decimal/row_index.astype(int) enforce today, one file at a time.
_REQUIRED_PARSED_COLUMNS = ["sensor_id", "row_index", "timestamp", "v3_raw", "t1_raw",
                            "t2_raw", "t3_raw", "signal_raw", "shake", "err_flag"]


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


def _bulk_parse_tms_files(entries: list[tuple[str, bytes]]) -> tuple[pd.DataFrame, list[str]]:
    """Parses many raw TOMST export files in a single DuckDB native CSV scan
    instead of one `pd.read_csv` + row-by-row timestamp-guessing loop per
    file (parse_tms_records) - the dominant cost once an upload reaches
    hundreds of files / millions of rows, since DuckDB's CSV reader is a
    single multi-threaded C++ scan across every file at once instead of N
    sequential Python calls.

    Applies the exact same per-file rule as parse_tms_records: any row with
    an unparseable required field (see _REQUIRED_PARSED_COLUMNS) rejects
    that entire file, not just the row - a fully blank line (e.g. a
    trailing newline) is not an error, it's silently skipped, matching
    pandas' default `skip_blank_lines` behaviour parse_tms_records relies on.

    Returns (good_df, bad_names) - bad_names are the entries that need to
    fall back to parse_tms_records (for a precise per-file error message),
    not a parse result themselves."""
    with tempfile.TemporaryDirectory(prefix="tms_bulk_") as tmp:
        tmp_path = Path(tmp)
        temp_paths = []
        for i, (name, content) in enumerate(entries):
            p = tmp_path / f"{i:05d}__{Path(name).name}"
            p.write_bytes(content if isinstance(content, bytes) else content.encode())
            temp_paths.append(p)

        columns_literal = "{" + ", ".join(f"'{c}': 'VARCHAR'" for c in RAW_FIELDS) + "}"
        format_coalesce = ", ".join(f"TRY_STRPTIME(timestamp_raw, '{fmt}')" for fmt in _DUCKDB_TIMESTAMP_FORMATS)
        decimal_cols = ["v3_raw", "t1_raw", "t2_raw", "t3_raw", "signal_raw", "shake", "err_flag"]
        decimal_select = ",\n            ".join(
            f"TRY_CAST(REPLACE({c}, ',', '.') AS DOUBLE) AS {c}" for c in decimal_cols
        )
        blank_check = " AND ".join(f"{c} IS NULL" for c in RAW_FIELDS if c != "v10_raw")

        query = f"""
        WITH raw AS (
            SELECT *, NULLIF(regexp_extract(filename, '/(\\d{{5}})__(.+)$', 2), '') AS orig_name
            FROM read_csv({store.sql_list_literal([str(p) for p in temp_paths])},
                           delim=';', header=false, null_padding=true, filename=true,
                           auto_detect=false, columns={columns_literal})
        ),
        parsed AS (
            SELECT
                orig_name,
                NULLIF(regexp_extract(orig_name, '(?i)data_(\\d+)_\\d{{4}}_\\d{{2}}_\\d{{2}}_\\d+\\.csv$', 1), '') AS sensor_id,
                orig_name AS source_file,
                TRY_CAST(row_index AS BIGINT) AS row_index,
                COALESCE({format_coalesce}) AS timestamp,
                {decimal_select},
                v10_raw,
                ({blank_check}) AS is_blank_line
            FROM raw
        )
        SELECT * FROM parsed WHERE NOT is_blank_line
        """
        df = store.sql_df(query, {})

    if df.empty:
        return df.reindex(columns=MERGED_EXPORT_COLUMNS), [name for name, _ in entries]

    all_names = {name for name, _ in entries}
    bad_mask = df[_REQUIRED_PARSED_COLUMNS].isna().any(axis=1)
    bad_from_rows = set(df.loc[bad_mask, "orig_name"])
    # a name present in `entries` but entirely absent from `df` (e.g. every
    # line in it was blank) is also a failure, not a silent success.
    missing_entirely = all_names - set(df["orig_name"].dropna())
    bad_names = sorted(bad_from_rows | missing_entirely)

    good_df = df.loc[~df["orig_name"].isin(bad_names)].drop(columns=["orig_name", "is_blank_line"], errors="ignore")
    good_df = good_df.reindex(columns=MERGED_EXPORT_COLUMNS)
    return good_df, bad_names


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


def _expand_zip(content: bytes) -> list[tuple[str, bytes]]:
    """Expands a .zip into (filename, content) pairs, skipping directories,
    hidden/system entries (.DS_Store, __MACOSX/...), and non-.csv members."""
    out = []
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        for info in zf.infolist():
            member_name = Path(info.filename).name
            if info.is_dir() or member_name.startswith(".") or "__MACOSX" in info.filename:
                continue
            if not member_name.lower().endswith(".csv"):
                continue
            out.append((member_name, zf.read(info)))
    return out


def write_tms_raw_uploads_to_store(uploaded_files: list, out_dir: Path, batch_size: int = UPLOAD_BATCH_SIZE
                                    ) -> tuple[list[Path], list[tuple[str, str]]]:
    """Load from a list of file-like objects (e.g. FastAPI's UploadFile).
    Each entry is a raw TOMST export, a merged raw archive, or a .zip of
    either (mixable in one upload).

    Raw TOMST exports (the overwhelming majority on a real multi-file
    session) are parsed in bulk per batch via _bulk_parse_tms_files - one
    native DuckDB CSV scan across up to `batch_size` files at once, instead
    of `batch_size` sequential `pd.read_csv` + row-by-row timestamp-guessing
    calls (parse_tms_records). Only the (normally few-to-none) files that
    scan flags as malformed fall back to parse_tms_records one at a time,
    to recover the exact per-file error message. Merged raw archive
    "resume" uploads (rare - see looks_like_merged_export) keep using their
    own dedicated parser, already a single well-formed CSV read. Each batch
    is written to Parquet as one part, not one part per input file - see
    the batching rationale on the old per-file version this replaced.

    Returns (paths, failures), with failures as
    [(filename, error message), ...] for any file that didn't parse - one
    bad file is skipped rather than aborting the whole upload."""
    entries = []
    for f in uploaded_files:
        name = getattr(f, "name", "")
        content = f.getvalue() if hasattr(f, "getvalue") else f.read()
        if name.lower().endswith(".zip"):
            members = _expand_zip(content)
            logger.info("TMS upload: %r expanded to %d file(s)", name, len(members))
            entries.extend(members)
        else:
            entries.append((name, content))

    total = len(entries)
    out_dir.mkdir(parents=True, exist_ok=True)
    for p in out_dir.glob("part_*.parquet"):
        p.unlink()
    paths = []
    failures = []
    logger.info("TMS upload: parsing %d file(s) in batches of %d", total, batch_size)
    for batch_start in range(0, total, batch_size):
        batch = entries[batch_start:batch_start + batch_size]
        batch_end = batch_start + len(batch)
        logger.info("TMS upload: batch %d-%d of %d", batch_start + 1, batch_end, total)

        is_merged = [looks_like_merged_export(c) for _, c in batch]
        merged_batch = [nc for nc, m in zip(batch, is_merged) if m]
        raw_batch = [nc for nc, m in zip(batch, is_merged) if not m]

        batch_frames = []
        for name, content in merged_batch:
            try:
                batch_frames.append(parse_merged_export(content))
            except Exception as e:
                logger.warning("TMS upload: failed to parse %r: %s", name, e)
                failures.append((name, str(e)))

        if raw_batch:
            try:
                good_df, bad_names = _bulk_parse_tms_files(raw_batch)
            except Exception as e:
                # the whole bulk scan failed structurally (not a per-file
                # data issue) - fall back to the slow, safe per-file path
                # for this entire batch rather than losing it.
                logger.warning("TMS upload: bulk parse failed for batch %d-%d (%s), falling back per-file",
                                batch_start + 1, batch_end, e)
                good_df, bad_names = pd.DataFrame(columns=MERGED_EXPORT_COLUMNS), [n for n, _ in raw_batch]
            if not good_df.empty:
                batch_frames.append(good_df)
            bad_content = dict(raw_batch)
            for name in bad_names:
                try:
                    batch_frames.append(parse_tms_records(name, bad_content[name]))
                except Exception as e:
                    logger.warning("TMS upload: failed to parse %r: %s", name, e)
                    failures.append((name, str(e)))

        if batch_frames:
            batch_df = pd.concat(batch_frames, ignore_index=True) if len(batch_frames) > 1 else batch_frames[0]
            paths.append(store.write_parquet(batch_df, out_dir / f"part_{len(paths):05d}.parquet"))
    logger.info("TMS upload: %d/%d file(s) parsed successfully (%d part file(s) written), %d failed",
                total - len(failures), total, len(paths), len(failures))
    if not paths:
        raise ValueError(f"No TMS files could be parsed ({len(failures)} failed)")
    return paths, failures
