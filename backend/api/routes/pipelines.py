"""API routes for running pipelines and checking job status."""
from fastapi import APIRouter, UploadFile, HTTPException, Form, File
from fastapi.responses import JSONResponse
from typing import List, Optional
from uuid import uuid4
from pathlib import Path
import json
import logging

from rq.job import Job
from rq.registry import StartedJobRegistry, FinishedJobRegistry, FailedJobRegistry

from backend.workers.connection import default_queue, high_queue, redis_conn
from backend.workers import tasks
from backend.api.models.pipeline import (
    TMSPipelineConfig,
    PipelineRunResponse,
    JobStatusResponse,
    JobListResponse
)
from backend.api.services.metadata import create_processing_run, update_run_status
from backend.pipeline import store

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])
logger = logging.getLogger(__name__)


@router.post("/tms/run", response_model=PipelineRunResponse)
async def run_tms_pipeline(
    files: List[UploadFile] = File(..., description="TOMST .TMS files"),
    config: str = Form(..., description="JSON-encoded TMS pipeline configuration"),
    user: str = Form(..., description="User email or name")
):
    """Upload TOMST files and start a TMS pipeline run."""
    # Parse config
    try:
        config_dict = json.loads(config)
        pipeline_config = TMSPipelineConfig(**config_dict)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid config: {e}")

    # Create session
    session_id = str(uuid4())
    session_dir = store.session_dir(session_id, "tms")
    uploads_dir = session_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded files
    # TMS pipeline accepts: .csv (TOMST exports), .TMS (binary), .xlsx (metadata)
    ALLOWED_TMS_EXTENSIONS = ('.csv', '.TMS', '.xlsx', '.zip')
    raw_file_paths = []
    for file in files:
        if not any(file.filename.lower().endswith(ext.lower()) for ext in ALLOWED_TMS_EXTENSIONS):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {file.filename}. Allowed: {', '.join(ALLOWED_TMS_EXTENSIONS)}"
            )

        file_path = uploads_dir / file.filename
        with open(file_path, 'wb') as f:
            content = await file.read()
            f.write(content)

        raw_file_paths.append(str(file_path))
        logger.info(f"Uploaded {file.filename} ({len(content)} bytes) to {file_path}")

    # Create processing run record
    run_id = create_processing_run(
        session_id=session_id,
        pipeline_type="tms",
        config=pipeline_config.dict(),
        user_email=user
    )

    # Enqueue job
    job = default_queue.enqueue(
        tasks.run_tms_pipeline,
        session_id=session_id,
        raw_files=raw_file_paths,
        config=pipeline_config.dict(),
        user=user,
        job_timeout='30m',
        result_ttl=86400,
        failure_ttl=3600,
        meta={
            'run_id': str(run_id),
            'session_id': session_id,
            'pipeline_type': 'tms',
            'user': user,
            'progress': 0,
            'current_stage': 'queued'
        }
    )

    # Update run record
    from backend.api.services.metadata import get_metadata_con
    with get_metadata_con() as con:
        con.execute(
            "UPDATE processing_runs SET job_id = ?, status = 'queued' WHERE run_id = ?",
            [job.id, run_id]
        )

    logger.info(f"Enqueued TMS pipeline job {job.id} for session {session_id}")

    return PipelineRunResponse(
        job_id=job.id,
        session_id=session_id,
        status="queued",
        queue_position=len(default_queue)
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Get RQ job status and progress.

    Frontend should poll this endpoint every 1-2 seconds while job is running.
    """
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    response = JobStatusResponse(
        job_id=job.id,
        status=job.get_status(),
        created_at=job.created_at,
        started_at=job.started_at,
        ended_at=job.ended_at
    )

    # Add progress metadata (set by worker tasks)
    if job.meta:
        response.progress = job.meta.get('progress', 0)
        response.current_stage = job.meta.get('current_stage')
        response.message = job.meta.get('message')
        response.session_id = job.meta.get('session_id')

    # Add result if finished
    if job.is_finished:
        response.result = job.result

    # Add error if failed
    if job.is_failed:
        response.error = str(job.exc_info) if job.exc_info else "Unknown error"

    return response


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a queued or running job."""
    try:
        job = Job.fetch(job_id, connection=redis_conn)

        if job.is_finished:
            raise HTTPException(status_code=400, detail="Cannot cancel finished job")

        job.cancel()
        job.delete()

        logger.info(f"Cancelled job {job_id}")
        return {"message": f"Job {job_id} cancelled"}

    except Exception as e:
        if "Job not found" in str(e):
            raise HTTPException(status_code=404, detail="Job not found")
        raise


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """List recent jobs (for admin/debugging).

    Query params:
        status: Filter by status (started, finished, failed, queued)
        limit: Max results (default 50)
        offset: Pagination offset
    """
    jobs_data = []

    if status == "started":
        registry = StartedJobRegistry(queue=default_queue)
        job_ids = registry.get_job_ids()[offset:offset+limit]
    elif status == "finished":
        registry = FinishedJobRegistry(queue=default_queue)
        job_ids = registry.get_job_ids()[offset:offset+limit]
    elif status == "failed":
        registry = FailedJobRegistry(queue=default_queue)
        job_ids = registry.get_job_ids()[offset:offset+limit]
    elif status == "queued" or status is None:
        # Jobs currently in queue
        all_jobs = default_queue.jobs
        job_ids = [j.id for j in all_jobs[offset:offset+limit]]
    else:
        raise HTTPException(status_code=400, detail=f"Invalid status filter: {status}")

    # Fetch job details
    for job_id in job_ids:
        try:
            job = Job.fetch(job_id, connection=redis_conn)
            jobs_data.append({
                "id": job.id,
                "status": job.get_status(),
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "meta": job.meta
            })
        except Exception:
            continue

    return JobListResponse(
        jobs=jobs_data,
        total=len(job_ids)
    )
