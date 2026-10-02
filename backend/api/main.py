"""FastAPI application entrypoint."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s"
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sensor Data Processor API",
    description="Backend API for sensor data cleaning and homogenization pipelines",
    version="2.0.0"
)

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # React dev servers
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from backend.api.routes import pipelines, datasets, sessions, metadata, qc_config, file_preview

app.include_router(pipelines.router)
app.include_router(datasets.router)
app.include_router(sessions.router)
app.include_router(metadata.router)
app.include_router(qc_config.router)
app.include_router(file_preview.router)

@app.get("/")
async def root():
    return {
        "message": "Sensor Data Processor API",
        "version": "2.0.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health():
    """Health check endpoint."""
    from backend.workers.connection import redis_conn

    try:
        redis_conn.ping()
        redis_status = "ok"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        redis_status = "error"

    return {
        "status": "ok",
        "redis": redis_status
    }
