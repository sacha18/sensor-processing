"""Pydantic models for dataset management."""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


class PublishDatasetRequest(BaseModel):
    """Request to publish a dataset after pipeline completion."""
    session_id: str = Field(description="Pipeline session ID with results")
    title: str = Field(description="Dataset display name", min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, description="Detailed description")
    pipeline_type: str = Field(description="tms")
    created_by: str = Field(description="User email or name")
    tags: list[str] = Field(default_factory=list, description="Search tags")
    raw_data_source: Optional[str] = Field(default=None, description="Description of input data")


class DatasetResponse(BaseModel):
    """Published dataset metadata."""
    dataset_id: UUID
    title: str
    description: Optional[str]
    pipeline_type: str
    created_by: str
    created_at: datetime
    raw_data_source: Optional[str]
    raw_data_hash: Optional[str]
    output_path: str
    output_checksum: str
    row_count: Optional[int]
    sensor_count: Optional[int]
    date_range_start: Optional[datetime]
    date_range_end: Optional[datetime]
    tags: list[str]
    status: str

    class Config:
        from_attributes = True


class DatasetListResponse(BaseModel):
    """Paginated list of datasets."""
    datasets: list[DatasetResponse]
    total: int
    limit: int
    offset: int


class DatasetConfigResponse(BaseModel):
    """Full reproducible configuration for a dataset."""
    dataset_id: UUID
    title: str
    pipeline_type: str
    config: dict = Field(description="Complete pipeline configuration")
    manual_edits: Optional[dict] = Field(default=None)
    metadata_table: Optional[dict] = Field(default=None)
    correction_table: Optional[dict] = Field(default=None)
    calibration_table: Optional[dict] = Field(default=None)
