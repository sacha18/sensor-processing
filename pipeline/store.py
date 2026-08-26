"""DuckDB + Parquet backed persistence and per-stage caching.

Replaces holding whole pipeline results in memory (`st.session_state` /
`st.cache_data`): each pipeline stage reads its inputs from Parquet files on
disk (via DuckDB), computes, and writes its output back to Parquet, cached on
disk and keyed by a hash of its own inputs + parameters - independently of
every other stage, and persisted across app/container restarts (unlike
Streamlit's in-memory cache).

DuckDB itself is an embedded (in-process) engine, not a server - there's no
connection to keep alive across reruns. The Parquet files on disk are the
actual state; a DuckDB connection is opened on demand to read/write them.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
import time
import uuid
from pathlib import Path

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

STORE_DIR = Path(os.environ.get("SDP_STORE_DIR", "./data/store")).resolve()
STORE_TTL_DAYS = float(os.environ.get("SDP_STORE_TTL_DAYS", "7"))


def new_session_id() -> str:
    return uuid.uuid4().hex


def session_dir(session_id: str, pipeline: str) -> Path:
    d = STORE_DIR / "sessions" / session_id / pipeline
    d.mkdir(parents=True, exist_ok=True)
    return d


def cleanup_old_sessions(ttl_days: float = STORE_TTL_DAYS, base_dir: Path = None) -> int:
    """Removes session directories whose most recently written file is older
    than `ttl_days` - called once at app startup. The store now persists data
    to disk across restarts (unlike the old in-memory-only session_state), so
    without this, disk usage would grow unbounded across many
    upload/parameter-tweak sessions."""
    base_dir = Path(base_dir) if base_dir else (STORE_DIR / "sessions")
    if not base_dir.exists():
        return 0
    cutoff = time.time() - ttl_days * 86400
    removed = 0
    for session in base_dir.iterdir():
        if not session.is_dir():
            continue
        try:
            newest = max((p.stat().st_mtime for p in session.rglob("*") if p.is_file()), default=session.stat().st_mtime)
        except OSError:
            continue
        if newest < cutoff:
            _rmtree(session)
            removed += 1
    if removed:
        logger.info("store cleanup: removed %d stale session dir(s) older than %g day(s)", removed, ttl_days)
    return removed


def _rmtree(path: Path) -> None:
    import shutil
    shutil.rmtree(path, ignore_errors=True)


def con() -> duckdb.DuckDBPyConnection:
    """A fresh in-process connection. Cheap to open (in-memory catalog, no
    handshake) - opened per call rather than held open across Streamlit
    reruns/threads, since the Parquet files are the real state."""
    return duckdb.connect(":memory:")


def write_parquet(df: pd.DataFrame, path: Path) -> Path:
    """Atomic write (via a temp file + rename) so a reader never sees a
    partially-written file - relevant once the same store dir can be read
    concurrently by another Streamlit session thread."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    with con() as c:
        c.register("_df", df)
        c.execute(f"COPY _df TO '{tmp.as_posix()}' (FORMAT PARQUET)")
    tmp.replace(path)
    return path


def _glob_args(paths) -> list:
    if isinstance(paths, (str, Path)):
        return [str(paths)]
    return [str(p) for p in paths]


def sql_list_literal(values: list[str]) -> str:
    """Escapes and formats a Python list of strings as a DuckDB SQL array
    literal, e.g. for a CREATE VIEW/read_csv() call where a prepared
    statement parameter can't be used."""
    return "[" + ", ".join("'" + v.replace("'", "''") + "'" for v in values) + "]"


def _normalize_datetimes(df: pd.DataFrame) -> pd.DataFrame:
    """DuckDB's TIMESTAMP is microsecond-precision, so a query result lands
    back in pandas as `datetime64[us]` - but every datetime column elsewhere
    in these pipelines (parsed via plain `pd.to_datetime`) is `datetime64[ns]`.
    Same instants either way, but mixing units invites subtle equality/dtype
    surprises downstream - normalized back to ns right after every query."""
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]) and getattr(df[col].dtype, "unit", "ns") != "ns":
            # .dt.as_unit (not .astype) - preserves a timezone-aware dtype,
            # which a plain .astype("datetime64[ns]") rejects outright.
            df[col] = df[col].dt.as_unit("ns")
    return df


class LazyFrameDict(dict):
    """A dict of {key: Path|list[Path]} that materializes each entry into a
    pandas DataFrame (or via a custom loader) only the first time it's
    actually accessed - a single pipeline step's render() typically touches
    a handful of the full pipeline's ~10 stage outputs, so eagerly reading
    every stage on every rerun (as a plain dict-of-DataFrames would) holds
    far more in memory at once than any one render needs. A plain
    `d[key] = df` assignment (e.g. ui.generic.overrides mutating "production"
    in place) still works normally and short-circuits future lazy loads for
    that key."""

    def __init__(self, paths: dict, loaders: dict = None):
        super().__init__()
        self._paths = paths
        self._loaders = loaders or {}

    def __missing__(self, key):
        loader = self._loaders.get(key, read_df)
        value = loader(self._paths[key])
        self[key] = value
        return value


class LazyDict(dict):
    """A dict of {key: zero-arg callable} where the callable only runs the
    first time that key is actually accessed via [] - used to make
    process_pipeline()/process_tms_pipeline()'s stage chain lazy so e.g.
    landing on the TMS "Metadata" step only computes merge/metadata, not
    every stage all the way through production. Each resolver typically
    calls other (`functools.cache`-memoized, so free on a second call
    within the same pipeline run) stage functions that may themselves
    trigger their own upstream store.stage() computation on first call."""

    def __init__(self, resolvers: dict):
        super().__init__()
        self._resolvers = resolvers

    def __missing__(self, key):
        value = self._resolvers[key]()
        self[key] = value
        return value


def read_df(paths, columns: list[str] = None, where_sql: str = None) -> pd.DataFrame:
    """Reads one or more Parquet files/globs into a single DataFrame, with
    optional column/predicate pushdown (only pulls what's asked for instead
    of materializing the whole stage output)."""
    cols = ", ".join(columns) if columns else "*"
    where = f" WHERE {where_sql}" if where_sql else ""
    with con() as c:
        df = c.execute(
            f"SELECT {cols} FROM read_parquet($paths){where}", {"paths": _glob_args(paths)}
        ).df()
    return _normalize_datetimes(df)


def sql_df(query: str, sources: dict[str, object] = None) -> pd.DataFrame:
    """Runs an arbitrary SQL query against named sources - each key in
    `sources` becomes a view (backed by a Parquet path/glob, or a pandas
    DataFrame passed straight through for small in-memory tables like a
    config/params table). Used for the set-based joins (metadata/correction/
    calibration/field-events) that replace per-row `.iterrows()` + full-table
    boolean-mask loops."""
    with con() as c:
        for name, source in (sources or {}).items():
            if isinstance(source, pd.DataFrame):
                c.register(name, source)
            else:
                # CREATE VIEW can't take a prepared-statement parameter in
                # DuckDB - inline an escaped SQL list literal instead.
                literal = sql_list_literal(_glob_args(source))
                c.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet({literal})")
        df = c.execute(query).df()
    return _normalize_datetimes(df)


def _file_sig(path: Path) -> tuple:
    try:
        st = Path(path).stat()
        return (str(path), st.st_size, st.st_mtime_ns)
    except OSError:
        return (str(path), None, None)


def _normalize_numbers(obj):
    """Recursively coerces int/float (and numpy numeric scalars) to plain
    float before hashing - a widget round-trip (e.g. `float(c["hampel_k"])`
    on a value that started as the int 6) can flip a config value's Python
    type without changing what it means, and `json.dumps(6)` != `json.dumps(6.0)`
    would otherwise register that as a real change, invalidating every
    downstream stage's cache for nothing."""
    if isinstance(obj, dict):
        return {k: _normalize_numbers(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize_numbers(v) for v in obj]
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, float)) or (hasattr(obj, "dtype") and hasattr(obj, "item")):
        return float(obj)
    return obj


def _jsonable(params: dict) -> dict:
    return json.loads(json.dumps(_normalize_numbers(params), sort_keys=True, default=str))


def _stage_key(inputs: list, params: dict) -> str:
    payload = {"inputs": [_file_sig(p) for p in inputs], "params": _jsonable(params or {})}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _hash_path(dir_: Path, name: str) -> Path:
    return dir_ / f"{name}.hash.json"


def _read_manifest(hash_path: Path) -> dict | None:
    try:
        return json.loads(hash_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def stage(dir_: Path, name: str, inputs: list, params: dict, compute_fn, on_compute=None) -> dict[str, Path]:
    """Runs `compute_fn()` only if the hash of `inputs` (existing file paths -
    hashed cheaply via size+mtime, not full content) + `params` differs from
    the last recorded run for this stage; otherwise reuses what's already on
    disk. This is the per-stage replacement for the old whole-pipeline
    `@st.cache_data`: changing one late-stage parameter only recomputes that
    stage, not everything upstream of it.

    `compute_fn()` must return one of:
      - a single DataFrame -> written as `<name>.parquet`
      - a dict of {output_name: DataFrame} -> written as `<name>__<output_name>.parquet`
        (main output should be named "main" -> `<name>.parquet`)
      - anything else picklable (e.g. the generic pipeline's heterogeneous
        `sim` dict: DataFrames + a numpy linkage array + a dict) -> written as
        `<name>.pkl`. Non-tabular by nature, not a freeze hotspot (see plan),
        so it's persisted for cache-hit purposes rather than forced into Parquet.

    `on_compute(name)`, if given, is called right before `compute_fn()` runs
    on a cache miss (never on a cache hit) - lets a caller with a UI (e.g.
    ui/*/data_source.py via st.status) show live "now computing X" progress
    instead of the whole page just looking frozen for however long the
    stage takes.

    Returns {output_name: Path} - {"main": path} for a single-DataFrame/pickle stage.
    """
    dir_ = Path(dir_)
    key_hash = _stage_key(inputs, params)
    hash_path = _hash_path(dir_, name)
    cached = _read_manifest(hash_path)
    if cached is not None and cached.get("key") == key_hash:
        paths = {out: dir_ / fname for out, fname in cached["outputs"].items()}
        if all(p.exists() for p in paths.values()):
            logger.info("pipeline stage %r: cache hit", name)
            return paths
    logger.info("pipeline stage %r: cache miss, computing", name)
    if on_compute is not None:
        on_compute(name)
    t0 = time.time()
    result = compute_fn()
    compute_s = time.time() - t0

    outputs: dict[str, str] = {}
    paths: dict[str, Path] = {}
    t0 = time.time()
    if isinstance(result, pd.DataFrame):
        result = {"main": result}
    if isinstance(result, dict) and all(isinstance(v, pd.DataFrame) for v in result.values()):
        for out_name, df in result.items():
            fname = f"{name}.parquet" if out_name == "main" else f"{name}__{out_name}.parquet"
            write_parquet(df, dir_ / fname)
            outputs[out_name] = fname
            paths[out_name] = dir_ / fname
        row_count = len(next(iter(result.values())))
    else:
        fname = f"{name}.pkl"
        (dir_ / fname).write_bytes(pickle.dumps(result))
        outputs["main"] = fname
        paths["main"] = dir_ / fname
        row_count = None
    write_s = time.time() - t0

    logger.info("pipeline stage %r: computed in %.1fs (write %.1fs)%s", name, compute_s, write_s,
                f", {row_count:,} row(s)" if row_count is not None else "")

    hash_path.write_text(json.dumps({"key": key_hash, "outputs": outputs}))
    return paths


def load_pickle(path: Path):
    return pickle.loads(Path(path).read_bytes())
