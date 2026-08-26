# Sensor data processor

Cleaning/homogenization of sensor series (generic pipeline) and TOMST TMS-4
(soil) processing - Streamlit app, computations and cache on DuckDB +
Parquet.

## Run with Docker (recommended)

```bash
docker compose up --build
```

Then open **http://localhost:8501**.

Data (Parquet files, per-pipeline-step cache) is persisted in a Docker
volume named `sdp_data`, mounted at `/data` - it survives a container
restart (`docker compose restart`, image update, ...).

To stop:

```bash
docker compose down
```

(`docker compose down -v` also removes the volume, and therefore the stored
data).

### Configuration (optional)

Copy `.env.example` to `.env` to adjust:

- `SDP_STORE_TTL_DAYS` (default 7) - time before an inactive session is
  automatically purged, at app startup.
- `SENSOR_DATA_DIR` - data folder to use instead of the bundled sample
  dataset (generic pipeline only).

### Inspecting stored data (debug/ops)

DuckDB has no server mode - `duckdb-cli` is a one-off utility, not launched
by default:

```bash
docker compose run --rm duckdb-cli duckdb /data/store/sessions/<id>/<pipeline>
```

## Run without Docker

Requires Python 3.13 and the dependencies from `requirements.txt` (a
`.venv` virtual environment is already set up in this repo):

```bash
.venv/bin/streamlit run app.py
```

The app listens by default on **http://localhost:8501**.
