# Sensor Data Processor

A platform for cleaning, QC-ing, and homogenizing environmental sensor data. It currently implements one end-to-end pipeline:

- **TMS pipeline** — processing of TOMST TMS-4 soil sensor data (soil temperature, air temperature, soil moisture/VWC), including deployment metadata, signal correction, calibration, and field-event-aware QC.

It takes raw logger exports in, and produces a cleaned, gap-filled, documented dataset out — with every intermediate step cached, inspectable, and reproducible. The pipeline layer (`backend/pipeline/`) is split into a TMS-specific package and a shared, pipeline-agnostic toolbox, so a future second pipeline can reuse the common building blocks instead of starting from scratch.

## Architecture

```
┌─────────────────┐      HTTP/JSON       ┌──────────────────┐      enqueue       ┌───────────────────┐
│  React frontend  │ ───────────────────▶ │   FastAPI API    │ ─────────────────▶ │     RQ workers     │
│   (frontend/)    │ ◀─────────────────── │  (backend/api/)  │ ◀───────────────── │ (backend/workers/) │
└─────────────────┘      poll job status  └──────────────────┘    job metadata    └───────────────────┘
                                                    │                                        │
                                                    │           both read/write              │
                                                    ▼                                        ▼
                                           ┌──────────────────────────────────────────────────────┐
                                           │           backend/pipeline/ (shared computation code) │
                                           │        backend/pipeline/tms/        store.py          │
                                           └──────────────────────────────────────────────────────┘
                                                                     │
                                                                     ▼
                                                     DuckDB + Parquet on disk (/data/store)
```

- **Frontend** uploads raw files, configures a pipeline run, and polls job status. It never talks to DuckDB/Parquet directly — only through the API.
- **API** validates requests, writes uploaded files to a per-session directory, enqueues an RQ job, and exposes read endpoints (stage data, previews, published datasets) by querying the Parquet store directly (no job needed for reads).
- **Workers** run the actual pipeline (`backend/pipeline/tms/orchestrate.py`) in the background, reporting progress via RQ job metadata so the API can relay it to the frontend.
- **Storage** is DuckDB + Parquet, not a traditional database for the heavy data — each pipeline stage's output is cached as a Parquet file, keyed by a hash of its inputs and parameters, so changing a late-stage parameter only recomputes what depends on it. A separate lightweight metadata DuckDB file tracks published datasets.

### Services (`docker compose up`)

| Service | Image/Build | Port | Role |
|---|---|---|---|
| `frontend` | `frontend/` (Vite dev server) | 5173 | React SPA |
| `api` | `backend/` | 8000 | FastAPI app (`uvicorn backend.api.main:app`) |
| `worker` | `backend/` | — | RQ worker consuming `default`, `high`, `low` queues |
| `redis` | `redis:7-alpine` | 6379 | Job queue + job metadata store |
| `duckdb-cli` | `datacatering/duckdb` | — | One-off CLI for inspecting stored Parquet (profile `tools`) |

In production (`docker-compose.prod.yml`), the React app is built to static assets and served by an nginx container that also reverse-proxies `/api` and `/docs` to the FastAPI backend — see [DEPLOY.md](./DEPLOY.md).

## Backend (`backend/`)

FastAPI app, organized as:

```
backend/
├── api/
│   ├── main.py            # App entrypoint, CORS, router registration, /health
│   ├── routes/
│   │   ├── pipelines.py   # Run pipelines, poll/cancel/list jobs
│   │   ├── datasets.py    # Browse/publish/download/preview/analyze published datasets
│   │   ├── sessions.py    # Session lifecycle, per-stage data access, stage re-run
│   │   ├── metadata.py    # TMS metadata tables (seed/get/edit/upload/import)
│   │   ├── qc_config.py   # Get/update QC thresholds per session
│   │   └── file_preview.py# Parse an uploaded file for preview before running
│   ├── models/            # Pydantic request/response schemas
│   ├── queries/           # Reusable SQL query builders over the Parquet store
│   └── services/          # Business logic (e.g. metadata DB access)
├── workers/
│   ├── connection.py      # Redis connection + RQ queue definitions
│   └── tasks.py           # RQ job functions wrapping backend.pipeline.tms
├── pipeline/              # Shared computation code (see below) — framework-agnostic
├── validators/            # Validation for uploaded config tables
└── utils/
```

Key endpoints (full details and `curl` examples in [backend/README.md](./backend/README.md)):

- `POST /api/pipelines/tms/run` — upload files + config, get back a `job_id`
- `GET /api/pipelines/jobs/{job_id}` — poll status/progress (0–100%, current stage)
- `GET/PUT /api/sessions/{id}/qc-config/{pipeline_type}` — inspect/tune QC thresholds
- `GET/PUT /api/sessions/{id}/metadata/{table_name}` — deployment/correction/calibration tables
- `GET /api/sessions/{id}/stages/{stage_name}` — pull a specific stage's output for charting
- `POST /api/datasets` / `GET /api/datasets` / `GET /api/datasets/{id}/download` — publish and browse finished datasets

Interactive API docs: **http://localhost:8000/docs** (Swagger UI, generated from the Pydantic models).

## Frontend (`frontend/`)

React 19 + TypeScript SPA, built with Vite, Tailwind, Radix UI primitives, TanStack Query for server state, and Plotly for charts.

```
frontend/src/
├── pages/
│   ├── BrowseDatasets.tsx   # "/"      — search/filter published datasets
│   ├── RunPipeline.tsx      # "/run"   — start a new TMS run
│   ├── MyDrafts.tsx         # "/drafts"— in-progress sessions not yet published
│   ├── JobStatus.tsx        # "/jobs/:jobId"            — live progress polling
│   ├── PipelineWizard.tsx   # "/sessions/:sessionId/wizard" — step-by-step QC/config wizard
│   ├── DatasetDetail.tsx    # "/datasets/:id"           — published dataset view + analysis
│   └── steps/tms/           # Individual wizard steps
├── components/
│   ├── wizard/      # Stepper navigation
│   ├── run/         # Run-configuration forms (quick start, automated, column mapping)
│   ├── tms/         # Correction/calibration rule editors, field events, manual QC
│   ├── metadata/    # Metadata table upload/edit
│   ├── charts/      # Time series, before/after, daily/monthly stats, heatmaps (Plotly)
│   └── ui/          # Radix-based primitives (buttons, dialogs, etc.)
├── api/             # `client.ts` (fetch wrapper) + `hooks.ts` (TanStack Query hooks)
└── lib/, hooks/      # Utilities, theme, confirm/alert dialog providers
```

The app flow mirrors the pipeline stages: upload files + configure → RQ job runs → step through the wizard to review QC results, tune parameters, edit metadata/correction/calibration tables and manual QC overrides → publish the resulting dataset so it's browsable and downloadable.

## Shared pipeline code (`backend/pipeline/`)

This is what the API/workers actually execute — it has no knowledge of FastAPI or React (no web-framework imports at all), and could be driven by any other frontend.

### Storage layer — `backend/pipeline/store.py`

- DuckDB + Parquet backed, not in-memory caching.
- Each session gets its own directory: `STORE_DIR/sessions/<session_id>/<pipeline>/`.
- `store.stage(dir, name, inputs, params, compute_fn)` only recomputes a stage if its inputs (file path + mtime + size) or parameters changed; otherwise it reads the cached Parquet. This means tweaking one late-stage parameter (e.g. a QC threshold) doesn't re-run earlier stages.
- `store.LazyDict` / `store.LazyFrameDict` make pipeline results lazy — accessing an early stage doesn't force later ones to compute.
- Read/write helpers (`read_df`, `sql_df`, `write_parquet`) wrap DuckDB SQL over Parquet files, including joins across Parquet paths and in-memory DataFrames.

### TMS pipeline — `backend/pipeline/tms/`

Orchestrated by `orchestrate.py`, stages run in order:

1. **Load** (`io.py`) — parse TOMST binary downloads
2. **Merge & dedupe** (`continuity.py`) — combine files, detect continuity gaps
3. **Metadata** (`metadata.py`) — apply deployment info (sensor × location × time period)
4. **Initial QC** (`initial_qc.py`) — per-channel checks + field-event masking (`events.py`)
5. **Correction** (`correction.py`) — offset/multiplier/formula adjustments
6. **Calibration** (`calibration.py`) — VWC calibration curve application
7. **Final QC** (`final_qc.py`) — post-calibration quality checks
8. **Production** (`production.py`) — build the final dataset

Default per-channel QC thresholds live in `params.py`.

### Shared building blocks — `backend/pipeline/common/`

Pipeline-agnostic primitives, kept separate from `tms/` rather than baked into it, so a future second pipeline can reuse them instead of reimplementing or reaching into TMS's internals:

- `qc_flags.py` — the four flag methods (Hampel, flatline, percentile, rate-of-change), applied per channel by TMS's `initial_qc.py`/`final_qc.py`.
- `dedupe.py` — `dedupe_by_priority(df, partition_cols, order_by_sql)`, a DuckDB window-function helper that keeps one row per group ranked by a caller-supplied priority order. TMS ranks duplicates by parsed download date/part; a pipeline using it keeps its own duplicate-conflict report, since what counts as "conflicting" depends on its own value columns.

## Data flow at a glance

1. User uploads raw files via the React app → `POST /api/pipelines/tms/run`.
2. API writes files to `STORE_DIR/sessions/<id>/tms/uploads/` and enqueues an RQ job.
3. Worker runs the orchestration pipeline, writing each stage's Parquet output and reporting progress in RQ job metadata.
4. Frontend polls `GET /api/pipelines/jobs/{job_id}` until `finished`, then opens the wizard to walk through stage results, let the user tune QC/correction/calibration parameters (each change re-triggers only the affected stages), and resolve flagged points manually.
5. Once satisfied, the user publishes the session as a named dataset (`POST /api/datasets`), which records metadata (row/sensor counts, date range, checksums, full reproducible config) in the metadata DuckDB and makes it downloadable/browsable by anyone.

## Running the app

See [QUICKSTART.md](./QUICKSTART.md) for a 2-minute setup and [DEPLOY.md](./DEPLOY.md) for a full local-server deployment guide (Ubuntu/Debian, Docker Compose, nginx, backups).

```bash
cp .env.example .env
docker compose up --build

# Frontend:  http://localhost:5173
# API docs:  http://localhost:8000/docs
# RQ dashboard: http://localhost:9181
```

### Configuration

Set in `.env` (copy from `.env.example`):

- `SDP_STORE_TTL_DAYS` — days before an inactive session is auto-purged (default 30)
- `FRONTEND_API_URL` — API base URL used by the production nginx build

### Inspecting persisted data

```bash
docker compose run --rm duckdb-cli duckdb /data/store/sessions/<id>/<pipeline>
```

## Further reading

- [CLAUDE.md](./CLAUDE.md) — developer-oriented guide: adding a pipeline stage, modifying QC, cache-invalidation testing, store/session debugging.
- [backend/README.md](./backend/README.md) — full API reference with example requests/responses.
- [DEPLOY.md](./DEPLOY.md) — production deployment on a local server.
- [QUICKSTART.md](./QUICKSTART.md) — fastest path to a running instance.
