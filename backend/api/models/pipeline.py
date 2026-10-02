"""Pydantic models for pipeline execution requests/responses."""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


class TMSPipelineConfig(BaseModel):
    """Configuration for TMS soil sensor pipeline."""
    metadata_table: list[dict] = Field(default_factory=list, description="Deployment metadata")
    correction_table: list[dict] = Field(default_factory=list, description="Signal correction params")
    calibration_table: list[dict] = Field(default_factory=list, description="VWC calibration params")
    field_events: Optional[list[dict]] = Field(default=None, description="Field event windows")
    qc_cfg: dict = Field(default_factory=dict, description="Initial QC config")
    final_qc_cfg: dict = Field(default_factory=dict, description="Final QC config")
    step_min: Optional[int] = Field(default=None, description="Expected time step (minutes)")


class PipelineRunResponse(BaseModel):
    """Response when a pipeline run is enqueued."""
    job_id: str = Field(description="RQ job ID for tracking")
    session_id: str = Field(description="Pipeline session ID")
    status: str = Field(description="Initial status (queued)")
    queue_position: int = Field(description="Position in queue")


class JobStatusResponse(BaseModel):
    """Response with job execution status and progress."""
    job_id: str
    status: str = Field(description="queued|started|finished|failed|canceled")
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    progress: int = Field(default=0, description="Progress percentage (0-100)")
    current_stage: Optional[str] = Field(default=None, description="Current pipeline stage")
    message: Optional[str] = Field(default=None, description="Status message")
    session_id: Optional[str] = None
    result: Optional[dict] = Field(default=None, description="Result data if finished")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class JobListResponse(BaseModel):
    """List of jobs (for admin/debugging)."""
    jobs: list[dict]
    total: int
