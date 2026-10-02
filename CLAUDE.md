# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Sensor data cleaning and homogenization platform. Currently implements one pipeline:
- **TMS pipeline**: TOMST TMS-4 soil sensor processing

**Architecture:** React frontend → FastAPI → RQ workers → DuckDB + Parquet storage

## Running the Application

```bash
# Start all services (frontend + API + workers + Redis + RQ dashboard)
docker compose up --build

# Services:
# - Frontend:     http://localhost:5173
# - API:          http://localhost:8000
# - API Docs:     http://localhost:8000/docs (Swagger UI)
# - RQ Dashboard: http://localhost:9181 (job monitoring)
# - Redis:        localhost:6379
```

**Test the API:**
```bash
# Health check
curl http://localhost:8000/health

# Upload and run the TMS pipeline (multipart/form-data)
curl -X POST http://localhost:8000/api/pipelines/tms/run \
  -F "files=@sensor1.csv" \
  -F "config={}" \
  -F "user=test@example.com"
```

See `backend/README.md` for full API documentation.

### Configuration
Copy `.env.example` to `.env` to configure:
- `SDP_STORE_TTL_DAYS` (default 7) - auto-purge inactive sessions

### Inspecting persisted data
```bash
# DuckDB CLI for debugging stored sessions
docker compose run --rm duckdb-cli duckdb /data/store/sessions/<id>/<pipeline>
```

## Architecture

### Application Structure

**Frontend** (`frontend/`): React SPA. `src/pages/` holds one component per route (browse datasets, run a pipeline, job status, the step-by-step wizard, dataset detail); `src/components/wizard|tms|run|metadata|charts/` hold the reusable pieces each page assembles. API calls go through `src/api/client.ts` + `src/api/hooks.ts` (TanStack Query).

**Backend** (`backend/api/`): FastAPI app. `routes/` has one module per resource (pipelines, datasets, sessions, metadata, qc_config, file_preview); `models/` are the Pydantic request/response schemas; `queries/` are reusable SQL builders over the Parquet store.

**Workers** (`backend/workers/`): `tasks.py` defines the RQ job functions that wrap `backend.pipeline.tms` orchestration and report progress via RQ job metadata; `connection.py` sets up the Redis connection and queues.

**Pipeline package** (`backend/pipeline/`), shared by the API/workers and framework-agnostic (pure pandas/numpy, no web framework imports):
- `backend/pipeline/tms/` - TOMST TMS-4 soil sensor pipeline, self-contained with its own orchestration, configuration, I/O, and processing modules

**Shared building blocks** (`backend/pipeline/common/`) - pipeline-agnostic primitives, kept separate from `tms/` so a future second pipeline can reuse them instead of reimplementing:
- `common/qc_flags.py` - the four QC flag methods (Hampel, flatline, percentile, rate-of-change), applied per channel by TMS's `initial_qc.py`/`final_qc.py` (T1/T2/T3/Signal/VWC)
- `common/dedupe.py` - `dedupe_by_priority(df, partition_cols, order_by_sql)`, a DuckDB window-function "keep one row per group, ranked by priority" helper. TMS's `continuity.py` uses it to rank duplicate rows by parsed download date/part; a pipeline using it keeps its own duplicate-conflict report, since what counts as "conflicting" depends on its own value columns.

### Data Flow & Caching Architecture

**Core persistence layer**: `backend/pipeline/store.py`
- DuckDB + Parquet backed storage (not an in-memory cache)
- Per-session directories under `STORE_DIR/sessions/<session_id>/<pipeline>`
- Each pipeline stage caches independently, keyed by hash of inputs (file path + mtime + size) + parameters

**Key function**: `store.stage(dir, name, inputs, params, compute_fn, on_compute=None)`
- Only recomputes if input files or parameters changed
- Returns `{output_name: Path}` pointing to Parquet files
- Supports single DataFrame, dict of DataFrames, or pickle for non-tabular data
- Changing one late-stage parameter only recomputes that stage, not upstream stages

**Lazy evaluation**: `store.LazyDict` and `store.LazyFrameDict`
- Pipeline results dict only materializes stages when accessed
- Landing on early step doesn't compute later stages
- Each stage's `compute_fn` is `@lru_cache` decorated for single-call-per-pipeline-run guarantee

### TMS Pipeline Flow

Orchestration: `backend/pipeline/tms/orchestrate.py`

Stages (in order):
1. **Load** (`io.py`) - Parse TOMST binary downloads
2. **Merge & dedupe** (`continuity.py`) - Combine files, detect continuity gaps
3. **Metadata** (`metadata.py`) - Apply deployment info (sensor x location x time period)
4. **Initial QC** (`initial_qc.py`) - Per-channel Hampel/flatline/range/rate checks + field events
5. **Correction** (`correction.py`) - Signal adjustments (offset, multiplier, formula)
6. **Calibration** (`calibration.py`) - VWC calibration curve application
7. **Final QC** (`final_qc.py`) - Post-calibration quality checks
8. **Production** (`production.py`) - Build final dataset

Key files:
- `backend/pipeline/tms/params.py` - Channel-specific default QC thresholds
- `backend/pipeline/tms/events.py` - Field event windows that mask QC failures
- `backend/api/routes/metadata.py` - Per-session metadata/correction/calibration table CRUD (Excel/CSV upload)

### Frontend Organization

- `frontend/src/pages/RunPipeline.tsx` / `PipelineWizard.tsx` - Start a run, then step through its results
- `frontend/src/pages/steps/tms/` - One step component per wizard stage
- `frontend/src/components/wizard/` - Stepper navigation (gates progress until validation is complete)
- `frontend/src/components/tms/` - Correction/calibration rule editors, field events manager, manual QC editor
- `frontend/src/components/metadata/` - Metadata table upload/edit
- `frontend/src/components/charts/` - Plotly time series, before/after, daily/monthly stats, heatmaps
- `frontend/src/api/hooks.ts` - TanStack Query hooks wrapping every backend endpoint

### DuckDB Query Patterns

**Reading Parquet**:
```python
# Single or multiple files with column/predicate pushdown
df = store.read_df(paths, columns=["timestamp", "value"], where_sql="value > 0")

# SQL queries with named sources (Parquet paths or DataFrames)
df = store.sql_df(
    "SELECT * FROM obs LEFT JOIN meta USING (sensor_id)",
    sources={"obs": parquet_path, "meta": metadata_df}
)
```

**Writing Parquet**:
```python
# Atomic write (temp file + rename)
store.write_parquet(df, path)
```

**Datetime handling**: DuckDB returns `datetime64[us]`, normalized to `datetime64[ns]` for pandas consistency (`_normalize_datetimes`).

## Development Workflow

### Adding a new pipeline stage

1. **Computation logic**: Create `backend/pipeline/tms/new_stage.py` with a function returning DataFrame(s)
2. **Orchestration**: Add stage to `backend/pipeline/tms/orchestrate.py`:
   ```python
   @lru_cache(maxsize=None)
   def new_stage():
       return store.stage(
           d, "new_stage", [upstream()["main"]], {"param": value},
           lambda: compute_new_stage(store.read_df(upstream()["main"]), param),
           on_compute=on_compute,
       )
   ```
3. **Expose in LazyDict**: Add `"new_stage": lambda: new_stage()["main"]` to return dict
4. **Expose via API**: Add/extend an endpoint in `backend/api/routes/sessions.py` so the frontend can fetch the new stage's data
5. **Frontend step**: Add a step component under `frontend/src/pages/steps/tms/` and wire it into the wizard's step list

### Adding a second pipeline

Write a new `backend/pipeline/<name>/` package (own orchestration, config, I/O) and a new `run_<name>_pipeline` RQ job function in `backend/workers/tasks.py`, reusing `_make_progress_callback` and `_records_to_df` rather than re-deriving them, and `backend/pipeline/common/` for any genuinely pipeline-agnostic primitive (QC flag methods, the priority-dedup helper) instead of reimplementing it or reaching into `tms/`. Don't force the new pipeline's job function into the same shape as `run_tms_pipeline` if its job genuinely differs (config tables, wizard stage reruns, etc.) - see the module docstring in `tasks.py`.

### Modifying QC/outlier detection

Edit `backend/pipeline/tms/initial_qc.py` or `backend/pipeline/tms/final_qc.py`, defaults in `backend/pipeline/tms/params.py`. The underlying flag methods (Hampel, flatline, percentile, rate) live in `backend/pipeline/common/qc_flags.py`.

QC parameters are hashed into stage cache key - changing a threshold invalidates downstream cache.

### Working with field events

Field events mask QC failures during known disturbances:
- Defined in `backend/pipeline/tms/events.py`
- User-editable via the frontend's Field Events manager (`frontend/src/components/tms/FieldEventsManager.tsx`), backed by `backend/api/routes/metadata.py` (Excel/CSV upload with columns: sensor_id, start, end, event_type)
- Applied in `initial_qc.py` and `final_qc.py` via SQL window joins

### Manual QC editing

`frontend/src/components/tms/ManualQCEditor.tsx` lets a user draw a time-window exclusion directly on the chart (sensor + channel + start/end + reason) - the exact same shape as an uploaded field event (see `pipeline/tms/events.py` above), just authored interactively instead of via file upload. Edits are staged client-side in `localStorage` (`manual_qc_edits_<sessionId>`/`field_events_<sessionId>` in `FinalQCStep.tsx`) until applied, at which point they're merged into the session's `field_events` and sent along with a stage re-run (`POST /api/sessions/{id}/run-stage/{stage_name}`) - so they flow through the same `field_event_flags()` mechanism as uploaded events, nothing point-level is mutated in the cached stage output. `ManualQCHistory.tsx` lists the edits made so far.

### Testing cache invalidation

1. Change a parameter via the frontend (or `PUT /api/sessions/{id}/qc-config/{pipeline_type}`)
2. Check worker logs for "cache miss, computing" - only affected stage should recompute
3. Verify upstream stages log "cache hit"

### Debugging store/session issues

- Sessions older than `SDP_STORE_TTL_DAYS` are purged by `backend.pipeline.store.cleanup_old_sessions()` - nothing currently invokes this automatically, so run it manually (e.g. via a one-off script or cron) if disk usage needs bounding
- Session IDs are generated per pipeline run by the API (`backend.pipeline.store.new_session_id()`)
- Store directory: `$SDP_STORE_DIR/sessions/<session_id>/<pipeline>/`
- Each stage writes `<name>.parquet` or `<name>__<output>.parquet` plus `<name>.hash.json` manifest

## Key Dependencies

**Backend/pipeline** (`backend/requirements.txt`):
- **FastAPI 0.115.0** + **Uvicorn**: API server
- **RQ 1.16.2** + **Redis 5.2.0**: Async job queue
- **DuckDB 1.5.5**: Embedded SQL engine for Parquet I/O
- **Pandas 3.0.3**: DataFrames
- **NumPy 2.5.0**: Numerical operations

**Frontend** (`frontend/package.json`):
- **React 19** + **TypeScript**, built with **Vite**
- **TanStack Query**: Server state/caching
- **Plotly.js** (`react-plotly.js`): Interactive charts
- **Radix UI** + **Tailwind CSS**: UI primitives/styling
