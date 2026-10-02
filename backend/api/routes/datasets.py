"""API routes for dataset management (browse, publish, download)."""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from typing import Optional, List
from uuid import UUID
from pathlib import Path
import logging
import json

from backend.api.models.dataset import (
    PublishDatasetRequest,
    DatasetResponse,
    DatasetListResponse,
    DatasetConfigResponse
)
from backend.api.services import metadata
from backend.api.queries import (
    build_count_query,
    build_schema_query,
    build_sample_query,
    build_daily_stats_query,
    build_daily_group_means_query,
    build_monthly_stats_query,
    build_distribution_query,
    build_summary_stats_query,
)
from backend.pipeline import store

router = APIRouter(prefix="/api/datasets", tags=["datasets"])
logger = logging.getLogger(__name__)


@router.get("", response_model=DatasetListResponse)
async def list_datasets(
    search: Optional[str] = Query(None, description="Search by title"),
    pipeline_type: Optional[str] = Query(None, description="Filter by pipeline type (tms)"),
    tags: Optional[List[str]] = Query(None, description="Filter by tags"),
    status: str = Query("active", description="Filter by status"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset")
):
    """List published datasets with search and filters.

    Supports:
    - Full-text search on title
    - Filter by pipeline type
    - Filter by tags (OR logic)
    - Pagination
    """
    df = metadata.get_published_datasets(
        search=search,
        pipeline_type=pipeline_type,
        tags=tags,
        status=status,
        limit=limit,
        offset=offset
    )

    # Convert NaN to None for Pydantic validation
    import numpy as np
    df = df.replace({np.nan: None})

    datasets = [DatasetResponse(**row) for row in df.to_dict('records')]

    # Get total count for pagination
    total = len(datasets)  # Simplified - could query count separately

    return DatasetListResponse(
        datasets=datasets,
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(dataset_id: UUID):
    """Get a single dataset by ID."""
    dataset = metadata.get_dataset_by_id(dataset_id)

    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return DatasetResponse(**dataset)


@router.get("/{dataset_id}/config", response_model=DatasetConfigResponse)
async def get_dataset_config(dataset_id: UUID):
    """Get full reproducible configuration for a dataset.

    Use this to clone a pipeline with the same parameters.
    """
    dataset = metadata.get_dataset_by_id(dataset_id)

    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return DatasetConfigResponse(
        dataset_id=dataset_id,
        title=dataset["title"],
        pipeline_type=dataset["pipeline_type"],
        config=json.loads(dataset["config"]) if isinstance(dataset["config"], str) else dataset["config"],
        manual_edits=json.loads(dataset["manual_edits"]) if dataset.get("manual_edits") and isinstance(dataset["manual_edits"], str) else dataset.get("manual_edits"),
        metadata_table=json.loads(dataset["metadata_table"]) if dataset.get("metadata_table") and isinstance(dataset["metadata_table"], str) else dataset.get("metadata_table"),
        correction_table=json.loads(dataset["correction_table"]) if dataset.get("correction_table") and isinstance(dataset["correction_table"], str) else dataset.get("correction_table"),
        calibration_table=json.loads(dataset["calibration_table"]) if dataset.get("calibration_table") and isinstance(dataset["calibration_table"], str) else dataset.get("calibration_table")
    )


@router.get("/{dataset_id}/download")
async def download_dataset(dataset_id: UUID):
    """Download the Parquet file for a published dataset."""
    dataset = metadata.get_dataset_by_id(dataset_id)

    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    output_path = dataset["output_path"]

    from pathlib import Path
    if not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Dataset file not found on disk")

    # Return file with proper filename
    safe_title = "".join(c if c.isalnum() or c in "_ -" else "_" for c in dataset["title"])
    filename = f"{safe_title}.parquet"

    return FileResponse(
        path=output_path,
        media_type="application/octet-stream",
        filename=filename
    )


@router.get("/{dataset_id}/preview")
async def preview_dataset(dataset_id: UUID, limit: int = 1000):
    """Get a preview of the dataset for visualization (sampled data)."""
    import duckdb
    import pandas as pd

    dataset = metadata.get_dataset_by_id(dataset_id)

    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    output_path = Path(dataset["output_path"])

    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Dataset file not found on disk")

    try:
        # Read a sample of the data
        con = duckdb.connect()

        # Get total row count
        count_query = build_count_query(str(output_path))
        total_rows = con.execute(count_query).fetchone()[0]

        # Sample evenly distributed rows for visualization
        sample_size = min(limit, total_rows)
        sample_query = build_sample_query(str(output_path), sample_size, total_rows)

        df = con.execute(sample_query).df()
        con.close()

        # Convert to format suitable for Plotly
        if 'timestamp' not in df.columns:
            raise HTTPException(status_code=400, detail="Dataset does not have a timestamp column")

        # Get numeric columns (excluding metadata columns)
        metadata_cols = ['sensor_id', 'timestamp', 'datetime', 'date', 'time', 'id', 'index',
                        'depth_cm', 'install_id', 'row', 'transect', 'position_depth',
                        'correction_id', 'calibration_id']
        value_cols = [col for col in df.columns if df[col].dtype in ['float64', 'int64']
                      and col not in metadata_cols
                      and not any(pattern in col for pattern in ['_qc_', 'is_qc', 'is_final', '_id', '_label'])]

        # If we have sensor_id, pivot to create one series per sensor
        if 'sensor_id' in df.columns and value_cols:
            # Prefer final/corrected columns, then raw, then others
            preferred_order = ['_final', '_corrected', '_raw', 'vwc', 'signal', 'temp', 't1', 't2', 't3']
            value_col = None
            for pattern in preferred_order:
                matching = [col for col in value_cols if pattern in col.lower()]
                if matching:
                    value_col = matching[0]
                    break
            if not value_col:
                value_col = value_cols[0]

            result = {
                "timestamp": [],
                "values": {}
            }

            for sensor_id in df['sensor_id'].unique():
                sensor_data = df[df['sensor_id'] == sensor_id].sort_values('timestamp')
                if not result["timestamp"]:
                    result["timestamp"] = sensor_data['timestamp'].astype(str).tolist()
                result["values"][str(sensor_id)] = sensor_data[value_col].fillna(0).tolist()

            return result
        else:
            # Generic format: just return timestamps and all numeric columns
            result = {
                "timestamp": df['timestamp'].astype(str).tolist(),
                "values": {}
            }

            for col in value_cols[:5]:  # Limit to 5 series max
                result["values"][col] = df[col].fillna(0).tolist()

            return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to preview dataset: {str(e)}")


@router.post("", response_model=DatasetResponse, status_code=201)
async def publish_dataset(request: PublishDatasetRequest):
    """Publish a completed pipeline run as a named dataset.

    This creates a permanent record with:
    - Reproducible configuration (all params)
    - Output Parquet file
    - Metadata for search/browse
    """
    # Load production data from session
    try:
        session_dir = store.session_dir(request.session_id, request.pipeline_type)

        production_path = session_dir / "production.parquet"

        if not production_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Pipeline output not found for session {request.session_id}. "
                       "Make sure the pipeline completed successfully."
            )

        output_df = store.read_df(production_path)

    except Exception as e:
        logger.error(f"Failed to load pipeline output: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to load pipeline output: {e}")

    # Get config from processing_runs table (if available)
    with metadata.get_metadata_con() as con:
        run_result = con.execute(
            "SELECT config FROM processing_runs WHERE session_id = ? ORDER BY started_at DESC LIMIT 1",
            [request.session_id]
        ).df()

        if not run_result.empty:
            config = json.loads(run_result.iloc[0]['config'])
        else:
            # No run record - use empty config
            logger.warning(f"No processing_run found for session {request.session_id}")
            config = {}

    # Extract metadata, correction, and calibration tables from session files
    metadata_table = None
    correction_table = None
    calibration_table = None

    # Load metadata from config_metadata.json
    metadata_file = session_dir / "config_metadata.json"
    if metadata_file.exists():
        try:
            with open(metadata_file) as f:
                metadata_table = json.load(f)
            logger.info(f"Loaded metadata table: {len(metadata_table)} rows")
        except Exception as e:
            logger.warning(f"Failed to load metadata: {e}")

    # Load QC config (includes correction, calibration, field events)
    qc_config_file = session_dir / "config_qc.json"
    if qc_config_file.exists():
        try:
            with open(qc_config_file) as f:
                qc_data = json.load(f)
                correction_table = qc_data.get("correction_table")
                calibration_table = qc_data.get("calibration_table")
                if correction_table:
                    logger.info(f"Loaded correction table: {len(correction_table)} rules")
                if calibration_table:
                    logger.info(f"Loaded calibration table: {len(calibration_table)} rules")
        except Exception as e:
            logger.warning(f"Failed to load QC config: {e}")

    # Publish dataset
    try:
        dataset_id = metadata.save_published_dataset(
            title=request.title,
            pipeline_type=request.pipeline_type,
            created_by=request.created_by,
            config=config,
            output_df=output_df,
            description=request.description,
            raw_data_source=request.raw_data_source,
            tags=request.tags,
            metadata_table=metadata_table,
            correction_table=correction_table,
            calibration_table=calibration_table
        )

        logger.info(f"Published dataset {request.title} (ID: {dataset_id})")

        # Return the created dataset
        dataset = metadata.get_dataset_by_id(dataset_id)
        return DatasetResponse(**dataset)

    except Exception as e:
        logger.error(f"Failed to publish dataset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to publish dataset: {e}")


@router.get("/{dataset_id}/analysis")
async def get_dataset_analysis(
    dataset_id: UUID,
    analysis_type: str = Query("daily", description="Analysis type: daily, monthly, distribution"),
    limit: int = Query(10000, description="Max rows to analyze")
):
    """Get advanced analysis data for dataset visualization.

    Returns aggregated statistics, distributions, and group comparisons
    suitable for creating analysis charts (box plots, bars, time series).
    """
    import duckdb
    import numpy as np

    dataset = metadata.get_dataset_by_id(dataset_id)

    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    output_path = Path(dataset["output_path"])

    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Dataset file not found on disk")

    try:
        con = duckdb.connect()

        # Get dataset schema
        schema_query = build_schema_query(str(output_path))
        schema_df = con.execute(schema_query).df()
        columns = schema_df['column_name'].tolist()

        # Identify key columns
        has_timestamp = 'timestamp' in columns
        has_sensor_id = 'sensor_id' in columns

        # Find value columns (prefer final/corrected)
        metadata_cols = ['sensor_id', 'timestamp', 'datetime', 'date', 'time', 'id', 'index',
                        'depth_cm', 'install_id', 'row', 'transect', 'position_depth',
                        'correction_id', 'calibration_id', 'site', 'treatment', 'position']
        value_cols = [col for col in columns if col not in metadata_cols
                      and not any(pattern in col for pattern in ['_qc_', 'is_qc', 'is_final', '_id', '_label'])]

        # Select primary value column
        preferred_patterns = ['vwc_final', 'signal_corrected_final', '_final', '_corrected', 'vwc', 'signal', 'value']
        value_col = None
        for pattern in preferred_patterns:
            matching = [col for col in value_cols if pattern in col.lower()]
            if matching:
                value_col = matching[0]
                break
        if not value_col and value_cols:
            value_col = value_cols[0]

        if not value_col:
            raise HTTPException(status_code=400, detail="No suitable value column found")

        # Determine grouping columns (treatment, site, etc.)
        group_cols = [col for col in ['treatment', 'site', 'depth_cm', 'position'] if col in columns]

        if analysis_type == "daily" and has_timestamp:
            # Daily statistics per sensor and group
            query = build_daily_stats_query(
                str(output_path), value_col, has_sensor_id, group_cols, limit
            )
            df = con.execute(query).df()

            # Also compute group means (average across sensors per day)
            if has_sensor_id and group_cols:
                group_query = build_daily_group_means_query(
                    str(output_path), value_col, group_cols
                )
                group_df = con.execute(group_query).df()
                result = {
                    "per_sensor": df.replace({np.nan: None}).to_dict('records'),
                    "group_means": group_df.replace({np.nan: None}).to_dict('records')
                }
            else:
                result = {
                    "per_sensor": df.replace({np.nan: None}).to_dict('records'),
                    "group_means": []
                }

        elif analysis_type == "monthly" and has_timestamp:
            # Monthly statistics
            query = build_monthly_stats_query(
                str(output_path), value_col, has_sensor_id, group_cols, limit
            )
            df = con.execute(query).df()
            result = {
                "monthly_stats": df.replace({np.nan: None}).to_dict('records')
            }

        elif analysis_type == "distribution":
            # Get full distribution for box plots
            query = build_distribution_query(
                str(output_path), value_col, has_sensor_id, group_cols, limit
            )
            df = con.execute(query).df()
            result = {
                "distribution": df.replace({np.nan: None}).to_dict('records'),
                "value_column": value_col,
                "has_sensor_id": has_sensor_id,
                "group_columns": group_cols
            }

        elif analysis_type == "summary":
            # Overall summary statistics
            query = build_summary_stats_query(
                str(output_path), value_col, has_sensor_id, group_cols, limit
            )
            df = con.execute(query).df()
            result = {
                "summary": df.replace({np.nan: None}).to_dict('records'),
                "value_column": value_col
            }

        else:
            raise HTTPException(status_code=400, detail=f"Unknown analysis type: {analysis_type}")

        con.close()

        # Add metadata about available columns
        result["metadata"] = {
            "value_column": value_col,
            "has_sensor_id": has_sensor_id,
            "has_timestamp": has_timestamp,
            "group_columns": group_cols,
            "all_value_columns": value_cols[:10]  # Limit to first 10
        }

        return result

    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to analyze dataset: {str(e)}")


@router.delete("/{dataset_id}")
async def archive_dataset(dataset_id: UUID):
    """Archive a dataset (soft delete - sets status to 'archived').

    Does NOT delete the Parquet file.
    """
    dataset = metadata.get_dataset_by_id(dataset_id)

    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    with metadata.get_metadata_con() as con:
        con.execute(
            "UPDATE published_datasets SET status = 'archived' WHERE dataset_id = ?",
            [dataset_id]
        )

    logger.info(f"Archived dataset {dataset_id}")
    return {"message": f"Dataset {dataset_id} archived"}
