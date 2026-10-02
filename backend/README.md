# Sensor Data Processor - Backend API

FastAPI backend with RQ workers for sensor data pipeline processing.

## Architecture

```
React Frontend → FastAPI API → RQ Workers → DuckDB + Parquet
                      ↓           ↓
                    Redis      Pipeline/*
```

## Quick Start

### Development (Docker Compose)

```bash
# From project root
docker compose up --build

# Services:
# - API:          http://localhost:8000
# - Docs:         http://localhost:8000/docs  (Swagger UI)
# - RQ Dashboard: http://localhost:9181
# - Redis:        localhost:6379
```

### Local Development (without Docker)

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Start Redis (required)
redis-server

# Start API
uvicorn backend.api.main:app --reload --port 8000

# Start worker (separate terminal)
rq worker default high low --url redis://localhost:6379
```

## API Endpoints

### Pipelines

**POST /api/pipelines/tms/run**
- Upload TOMST .TMS files and start TMS pipeline
- Returns: `job_id` for tracking

**GET /api/pipelines/jobs/{job_id}**
- Get job status and progress (poll every 1s)
- Returns: status, progress (0-100), current_stage, result

**DELETE /api/pipelines/jobs/{job_id}**
- Cancel a queued/running job

**GET /api/pipelines/jobs**
- List recent jobs (admin/debug)
- Query params: `status`, `limit`, `offset`

### Datasets

**GET /api/datasets**
- List published datasets
- Query params: `search`, `pipeline_type`, `tags`, `limit`, `offset`

**GET /api/datasets/{id}**
- Get dataset metadata

**GET /api/datasets/{id}/config**
- Get full reproducible configuration (for cloning)

**GET /api/datasets/{id}/download**
- Download Parquet file

**POST /api/datasets**
- Publish a completed pipeline as a named dataset
- Body: `{session_id, title, description, pipeline_type, created_by, tags}`

**DELETE /api/datasets/{id}**
- Archive dataset (soft delete)

### Health

**GET /health**
- Health check (API + Redis status)

## Example Usage

### 1. Run the TMS Pipeline

```bash
# Upload files and start pipeline
curl -X POST http://localhost:8000/api/pipelines/tms/run \
  -F "files=@sensor1.csv" \
  -F "files=@sensor2.csv" \
  -F "config={\"qc_cfg\":{}}" \
  -F "user=researcher@example.com"

# Response:
{
  "job_id": "abc123",
  "session_id": "uuid-here",
  "status": "queued",
  "queue_position": 0
}
```

### 2. Poll Job Status

```bash
# Check progress (repeat every 1-2 seconds)
curl http://localhost:8000/api/pipelines/jobs/abc123

# Response (running):
{
  "job_id": "abc123",
  "status": "started",
  "progress": 60,
  "current_stage": "Filling gaps",
  "message": "Computing gap fill...",
  "session_id": "uuid-here"
}

# Response (completed):
{
  "job_id": "abc123",
  "status": "finished",
  "progress": 100,
  "result": {
    "status": "completed",
    "session_id": "uuid-here",
    "stages": ["merged", "with_metadata", "initial_qc", "production", ...]
  }
}
```

### 3. Publish Dataset

```bash
curl -X POST http://localhost:8000/api/datasets \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "uuid-from-job",
    "title": "Soil moisture study 2026",
    "description": "Field study with 20 sensors",
    "pipeline_type": "tms",
    "created_by": "researcher@example.com",
    "tags": ["soil", "2026", "field_a"]
  }'
```

### 4. Browse Datasets

```bash
# Search datasets
curl "http://localhost:8000/api/datasets?search=soil&limit=20"

# Get dataset config (for cloning)
curl http://localhost:8000/api/datasets/{id}/config

# Download Parquet
curl -O http://localhost:8000/api/datasets/{id}/download
```

## Configuration

Environment variables:

- `REDIS_URL` - Redis connection (default: `redis://localhost:6379`)
- `SDP_STORE_DIR` - Data storage directory (default: `./data/store`)
- `SDP_STORE_TTL_DAYS` - Session cleanup TTL (default: `7`)

## Development

### Project Structure

```
backend/
├── api/
│   ├── main.py           # FastAPI app
│   ├── routes/           # API endpoints
│   │   ├── pipelines.py  # Run pipelines, job status
│   │   └── datasets.py   # Browse, publish, download
│   ├── models/           # Pydantic schemas
│   └── services/         # Business logic (metadata DB)
├── workers/
│   ├── connection.py     # Redis + RQ queues
│   └── tasks.py          # Pipeline jobs (reuses pipeline/*)
├── pipeline/              # Shared computation code (TMS pipeline + common/ toolbox)
├── Dockerfile
└── requirements.txt
```

### Adding a New Endpoint

1. Define Pydantic models in `api/models/`
2. Create route in `api/routes/`
3. Import and include router in `api/main.py`
4. Update this README

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest backend/tests/
```

## Monitoring

**RQ Dashboard**: http://localhost:9181
- View queued/running/failed jobs
- Inspect job results and errors
- Manually retry failed jobs

**API Docs**: http://localhost:8000/docs
- Interactive Swagger UI
- Test endpoints directly
- View request/response schemas

## Troubleshooting

**Job stuck in "queued" status**
- Check worker is running: `docker compose logs worker`
- Check Redis: `redis-cli ping`

**Pipeline fails with "No raw data files found"**
- Ensure files were uploaded correctly
- Check uploads directory: `/data/store/sessions/{session_id}/{pipeline}/uploads/`

**Can't access metadata.duckdb**
- Check file permissions on `/data/` volume
- Ensure `SDP_STORE_DIR` is writable

**Worker crashes**
- Check logs: `docker compose logs worker`
- Increase timeout if pipeline is large: `job_timeout='60m'`

## Scaling

Run multiple workers:

```bash
# Scale to 5 workers
docker compose up --scale worker=5

# Workers process jobs in parallel from shared queue
```

Queue priorities:
- `high`: Urgent/small pipelines
- `default`: Normal pipelines (most use this)
- `low`: Batch jobs, exports
