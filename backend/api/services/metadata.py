"""DuckDB metadata service for published datasets, processing runs, and manual edits.

Stores reproducible processing history in /data/metadata.duckdb (persistent, shared
across sessions, survives container restarts).
"""
import duckdb
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
import os

import pandas as pd

logger = logging.getLogger(__name__)

# Metadata DB path (persistent, outside ephemeral /sessions/)
STORE_DIR = Path(os.environ.get("SDP_STORE_DIR", "./data/store")).resolve()
METADATA_DB = STORE_DIR.parent / "metadata.duckdb"
PUBLISHED_DIR = STORE_DIR.parent / "published"


def get_metadata_con() -> duckdb.DuckDBPyConnection:
    """Get a connection to the persistent metadata database.

    Creates tables on first connection if they don't exist.
    """
    METADATA_DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(METADATA_DB))
    _create_tables_if_not_exist(con)
    return con


def _create_tables_if_not_exist(con: duckdb.DuckDBPyConnection):
    """Create metadata tables if they don't already exist."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS published_datasets (
            dataset_id UUID PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            pipeline_type TEXT NOT NULL,  -- 'tms'
            created_by TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL,

            -- Input data tracking
            raw_data_source TEXT,  -- Description or path
            raw_data_hash TEXT,    -- SHA256 of input files

            -- Full reproducible configuration (JSON)
            config JSON NOT NULL,              -- All pipeline params
            manual_edits JSON,                 -- Manual QC overrides
            metadata_table JSON,               -- TMS: deployment metadata
            correction_table JSON,             -- TMS: signal correction
            calibration_table JSON,            -- TMS: VWC calibration

            -- Output dataset
            output_path TEXT NOT NULL,         -- /data/published/*.parquet
            output_checksum TEXT NOT NULL,     -- SHA256 for integrity
            row_count INTEGER,
            sensor_count INTEGER,
            date_range_start TIMESTAMP,
            date_range_end TIMESTAMP,

            -- Searchability
            tags TEXT[],
            status TEXT DEFAULT 'active'       -- active, archived, deprecated
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS processing_runs (
            run_id UUID PRIMARY KEY,
            session_id TEXT NOT NULL,
            pipeline_type TEXT NOT NULL,
            user_email TEXT,
            started_at TIMESTAMP NOT NULL,
            completed_at TIMESTAMP,
            status TEXT NOT NULL,  -- queued, running, completed, failed
            config JSON NOT NULL,
            error_message TEXT,
            job_id TEXT  -- RQ job ID for tracking
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS manual_edits (
            edit_id UUID PRIMARY KEY,
            run_id UUID,
            dataset_id UUID,
            sensor_id TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            original_value DOUBLE,
            override_value DOUBLE,
            reason TEXT,
            edited_by TEXT NOT NULL,
            edited_at TIMESTAMP NOT NULL,
            FOREIGN KEY (run_id) REFERENCES processing_runs(run_id),
            FOREIGN KEY (dataset_id) REFERENCES published_datasets(dataset_id)
        )
    """)

    # Indexes for performance
    con.execute("CREATE INDEX IF NOT EXISTS idx_datasets_title ON published_datasets(title)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_datasets_created ON published_datasets(created_at DESC)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_datasets_pipeline ON published_datasets(pipeline_type)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_datasets_status ON published_datasets(status)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_runs_session ON processing_runs(session_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_edits_dataset ON manual_edits(dataset_id)")


def save_published_dataset(
    title: str,
    pipeline_type: str,
    created_by: str,
    config: dict,
    output_df: pd.DataFrame,
    description: str = None,
    raw_data_source: str = None,
    raw_data_hash: str = None,
    manual_edits: dict = None,
    metadata_table: dict = None,
    correction_table: dict = None,
    calibration_table: dict = None,
    tags: list[str] = None
) -> UUID:
    """Save a published dataset with full reproducible configuration.

    Args:
        title: Dataset display name (searchable)
        pipeline_type: 'tms'
        created_by: User email/name
        config: Complete pipeline configuration (all params)
        output_df: Final production DataFrame
        description: Optional long description
        raw_data_source: Description of input files
        raw_data_hash: SHA256 hash of input files
        manual_edits: Dict of manual QC overrides
        metadata_table/correction_table/calibration_table: TMS-specific config
        tags: List of tags for search/filtering

    Returns:
        dataset_id (UUID)
    """
    dataset_id = uuid4()
    timestamp = datetime.now()

    # Save Parquet output to /data/published/
    PUBLISHED_DIR.mkdir(exist_ok=True, parents=True)
    safe_title = "".join(c if c.isalnum() or c in "_ -" else "_" for c in title)
    output_path = PUBLISHED_DIR / f"{safe_title}_{dataset_id.hex[:8]}.parquet"
    output_df.to_parquet(output_path, index=False)

    # Compute checksum
    output_checksum = hashlib.sha256(output_path.read_bytes()).hexdigest()

    # Extract dataset stats
    row_count = len(output_df)
    sensor_count = output_df["sensor_id"].nunique() if "sensor_id" in output_df.columns else None

    if "timestamp" in output_df.columns:
        date_range_start = output_df["timestamp"].min()
        date_range_end = output_df["timestamp"].max()
    else:
        date_range_start = date_range_end = None

    # Insert into database
    with get_metadata_con() as con:
        con.execute("""
            INSERT INTO published_datasets VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            dataset_id,
            title,
            description,
            pipeline_type,
            created_by,
            timestamp,
            raw_data_source,
            raw_data_hash,
            json.dumps(config),
            json.dumps(manual_edits) if manual_edits else None,
            json.dumps(metadata_table) if metadata_table else None,
            json.dumps(correction_table) if correction_table else None,
            json.dumps(calibration_table) if calibration_table else None,
            str(output_path),
            output_checksum,
            row_count,
            sensor_count,
            date_range_start,
            date_range_end,
            tags or [],
            'active'
        ))

    logger.info(f"Published dataset: {title} (ID: {dataset_id}, {row_count:,} rows)")
    return dataset_id


def get_published_datasets(
    search: str = None,
    pipeline_type: str = None,
    tags: list[str] = None,
    status: str = "active",
    limit: int = 100,
    offset: int = 0
) -> pd.DataFrame:
    """Query published datasets with filters.

    Returns DataFrame with all dataset metadata.
    """
    with get_metadata_con() as con:
        query = "SELECT * FROM published_datasets WHERE status = ?"
        params = [status]

        if search:
            query += " AND title ILIKE ?"
            params.append(f"%{search}%")

        if pipeline_type:
            query += " AND pipeline_type = ?"
            params.append(pipeline_type)

        if tags:
            # Match any tag in the array
            tag_conditions = " OR ".join(["list_contains(tags, ?)" for _ in tags])
            query += f" AND ({tag_conditions})"
            params.extend(tags)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        return con.execute(query, params).df()


def get_dataset_by_id(dataset_id: UUID) -> Optional[dict]:
    """Get a single dataset by ID, returns dict or None."""
    with get_metadata_con() as con:
        result = con.execute(
            "SELECT * FROM published_datasets WHERE dataset_id = ?",
            [dataset_id]
        ).df()

        if result.empty:
            return None

        # Convert NaN to None for Pydantic validation
        import numpy as np
        result = result.replace({np.nan: None})
        return result.iloc[0].to_dict()


def load_dataset_parquet(dataset_id: UUID) -> pd.DataFrame:
    """Load the Parquet output for a published dataset."""
    dataset = get_dataset_by_id(dataset_id)
    if not dataset:
        raise ValueError(f"Dataset {dataset_id} not found")

    output_path = Path(dataset["output_path"])
    if not output_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {output_path}")

    return pd.read_parquet(output_path)


def create_processing_run(
    session_id: str,
    pipeline_type: str,
    config: dict,
    user_email: str = None,
    job_id: str = None
) -> UUID:
    """Create a processing run record (for tracking pipeline execution)."""
    run_id = uuid4()

    with get_metadata_con() as con:
        con.execute("""
            INSERT INTO processing_runs
            (run_id, session_id, pipeline_type, user_email, started_at, status, config, job_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            session_id,
            pipeline_type,
            user_email,
            datetime.now(),
            'queued',
            json.dumps(config),
            job_id
        ))

    return run_id


def update_run_status(
    run_id: UUID,
    status: str,
    error_message: str = None
):
    """Update a processing run's status."""
    with get_metadata_con() as con:
        if status == 'completed':
            con.execute("""
                UPDATE processing_runs
                SET status = ?, completed_at = ?
                WHERE run_id = ?
            """, (status, datetime.now(), run_id))
        else:
            con.execute("""
                UPDATE processing_runs
                SET status = ?, error_message = ?
                WHERE run_id = ?
            """, (status, error_message, run_id))
