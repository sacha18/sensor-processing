"""API routes for session management and stage-level access."""
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from typing import Optional, List
from pathlib import Path
import logging
import uuid
import shutil
import json

from backend.api.queries import (
    build_stage_count_query,
    build_stage_sample_query,
    build_empty_schema_query
)
from backend.pipeline import store

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
logger = logging.getLogger(__name__)


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    pipeline_type: str = Query("tms", description="Pipeline type (tms)")
):
    """Delete a session and all its data."""
    try:
        import shutil

        session_dir = store.session_dir(session_id, pipeline_type)

        if not session_dir.exists():
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        # Delete entire session directory
        shutil.rmtree(session_dir)

        logger.info(f"Deleted session {session_id} ({pipeline_type})")

        return {
            "success": True,
            "message": f"Session {session_id} deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")


@router.get("/list")
async def list_sessions(
    pipeline_type: str = Query("tms", description="Pipeline type (tms)")
):
    """List all available sessions for a pipeline type.

    Returns sessions found in the store directory with their basic info.
    """
    try:
        store_base = Path(store.STORE_DIR) / "sessions"
        if not store_base.exists():
            return {"sessions": []}

        sessions = []

        # Scan all session directories
        for session_path in store_base.iterdir():
            if not session_path.is_dir():
                continue

            session_id = session_path.name
            pipeline_dir = session_path / pipeline_type

            if not pipeline_dir.exists():
                continue

            # Get session info
            session_info = {
                "session_id": session_id,
                "pipeline_type": pipeline_type,
                "last_modified": pipeline_dir.stat().st_mtime
            }

            # Check for status.json (automated run)
            status_file = pipeline_dir / "status.json"
            if status_file.exists():
                try:
                    with open(status_file) as f:
                        status_data = json.load(f)
                    session_info["status"] = status_data.get("status", "unknown")
                    session_info["is_automated"] = True
                except (json.JSONDecodeError, ValueError):
                    # Empty or malformed JSON, treat as manual
                    session_info["status"] = "manual"
                    session_info["is_automated"] = False
            else:
                session_info["status"] = "manual"
                session_info["is_automated"] = False

            # Count available stages
            stage_files = list(pipeline_dir.glob("*.parquet"))
            session_info["stage_count"] = len(stage_files)

            sessions.append(session_info)

        # Sort by last modified (newest first)
        sessions.sort(key=lambda x: x["last_modified"], reverse=True)

        return {"sessions": sessions}

    except Exception as e:
        logger.error(f"Failed to list sessions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create")
async def create_session(
    files: List[UploadFile] = File(...),
    pipeline_type: str = Form(...),
    user: str = Form("anonymous")
):
    """Create a new session and upload files without running pipeline.

    This creates a session directory and uploads files to the 'uploads' folder.
    The wizard steps can then trigger jobs as needed for processing.
    """
    try:
        # Generate session ID
        session_id = str(uuid.uuid4())
        session_dir = store.session_dir(session_id, pipeline_type)
        session_dir.mkdir(parents=True, exist_ok=True)

        # Create uploads directory
        uploads_dir = session_dir / "uploads"
        uploads_dir.mkdir(exist_ok=True)

        # Save uploaded files
        uploaded_files = []
        for file in files:
            file_path = uploads_dir / file.filename
            with open(file_path, 'wb') as f:
                shutil.copyfileobj(file.file, f)
            uploaded_files.append({
                "filename": file.filename,
                "size": file_path.stat().st_size
            })

        logger.info(f"Created session {session_id} with {len(files)} files for {user}")

        return {
            "session_id": session_id,
            "pipeline_type": pipeline_type,
            "user": user,
            "files": uploaded_files,
            "total_files": len(uploaded_files)
        }

    except Exception as e:
        logger.error(f"Failed to create session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-automated")
async def create_automated_session(
    files: List[UploadFile] = File(...),
    pipeline_type: str = Form(...),
    user: str = Form("anonymous"),
    source_dataset_id: Optional[str] = Form(None),
    metadata_file: Optional[UploadFile] = File(None),
    qc_params_file: Optional[UploadFile] = File(None),
    corrections_file: Optional[UploadFile] = File(None),
    calibrations_file: Optional[UploadFile] = File(None),
    metadata_mapping: Optional[str] = Form(None),
    corrections_mapping: Optional[str] = Form(None),
    calibrations_mapping: Optional[str] = Form(None)
):
    """Create a new session with configuration and start automated pipeline execution.

    This endpoint:
    1. Creates a session directory
    2. Uploads sensor data files
    3. Either copies config from a published dataset OR validates and saves uploaded config files
    4. Enqueues automated pipeline job
    5. Returns session info with job ID

    Args:
        files: Sensor data files (.csv, .TMS, .xlsx)
        pipeline_type: Pipeline type ("tms")
        user: User email/name
        source_dataset_id: Optional UUID of published dataset to copy config from
        metadata_file: Optional metadata CSV/JSON/XLSX
        qc_params_file: Optional QC parameters JSON
        corrections_file: Optional corrections CSV
        calibrations_file: Optional calibrations CSV

    Returns:
        dict with session_id, job_id, and status
    """
    try:
        from backend.validators import (
            validate_metadata_file,
            validate_qc_params_file,
            validate_corrections_file,
            validate_calibrations_file,
            ValidationError
        )
        from backend.api.routes.metadata import METADATA_SCHEMAS
        from backend.utils import copy_config_from_dataset
        from backend.workers.connection import default_queue
        from backend.workers import tasks

        # This endpoint's config handling (metadata/QC/correction/calibration
        # tables, dataset-config copying) is TMS-specific throughout - TMS is
        # currently the only pipeline this app supports.
        if pipeline_type != "tms":
            raise HTTPException(
                status_code=400,
                detail="Automated session creation is only supported for the TMS pipeline."
            )

        # Generate session ID
        session_id = str(uuid.uuid4())
        session_dir = store.session_dir(session_id, pipeline_type)
        session_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Creating automated session {session_id} for user {user}")

        # Create uploads directory and save sensor data files
        uploads_dir = session_dir / "uploads"
        uploads_dir.mkdir(exist_ok=True)

        uploaded_files = []
        for file in files:
            file_path = uploads_dir / file.filename
            with open(file_path, 'wb') as f:
                shutil.copyfileobj(file.file, f)
            uploaded_files.append({
                "filename": file.filename,
                "size": file_path.stat().st_size
            })

        logger.info(f"Uploaded {len(files)} sensor data files")

        # Handle configuration (supports hybrid mode)
        config_summary = {
            "metadata": False,
            "qc_params": False,
            "corrections": False,
            "calibrations": False
        }

        # Step 1: Copy config from dataset if provided
        if source_dataset_id:
            logger.info(f"Copying config from dataset {source_dataset_id}")

            try:
                from uuid import UUID
                dataset_uuid = UUID(source_dataset_id)
                copy_result = await copy_config_from_dataset(
                    dataset_id=dataset_uuid,
                    target_session_id=session_id,
                    pipeline_type=pipeline_type
                )

                config_summary = copy_result["copied"]
                logger.info(f"Config copied from dataset: {copy_result['message']}")

            except Exception as copy_error:
                logger.error(f"Failed to copy config from dataset: {copy_error}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to copy config from dataset: {str(copy_error)}"
                )

        # Parse column mappings from JSON strings
        metadata_col_mapping = json.loads(metadata_mapping) if metadata_mapping else {}
        corrections_col_mapping = json.loads(corrections_mapping) if corrections_mapping else {}
        calibrations_col_mapping = json.loads(calibrations_mapping) if calibrations_mapping else {}

        # Step 2: Process uploaded files (overrides dataset config if provided)
        # This supports:
        # - Pure upload mode (no source_dataset_id)
        # - Hybrid mode (source_dataset_id + some manual uploads)
        validation_results = {}

        # 1. Metadata file (merges with dataset metadata if uploaded)
        if metadata_file:
            try:
                # Read and parse uploaded file
                content = await metadata_file.read()

                import pandas as pd
                import io
                from pathlib import Path

                suffix = Path(metadata_file.filename).suffix.lower()
                if suffix == ".json":
                    data = json.loads(content.decode("utf-8"))
                    df_uploaded = pd.DataFrame(data)
                elif suffix == ".xlsx":
                    df_uploaded = pd.read_excel(io.BytesIO(content))
                else:  # CSV
                    df_uploaded = pd.read_csv(io.BytesIO(content))

                # Apply column mapping (rename columns from user mapping)
                if metadata_col_mapping:
                    # Reverse mapping: actualColumn -> expectedColumn
                    reverse_mapping = {v: k for k, v in metadata_col_mapping.items()}
                    df_uploaded.rename(columns=reverse_mapping, inplace=True)

                # Normalize column names (case-insensitive, trim whitespace)
                df_uploaded.columns = [col.strip().lower().replace(' ', '_') for col in df_uploaded.columns]

                # Now validate AFTER mapping and normalization
                # Check for required column
                if 'sensor_id' not in df_uploaded.columns:
                    raise ValidationError("Missing required column: 'sensor_id'")

                # Merge with existing metadata from dataset (if it exists)
                metadata_path = session_dir / "config_metadata.json"
                if metadata_path.exists():
                    # Load existing metadata from dataset
                    with open(metadata_path, 'r') as f:
                        existing_data = json.load(f)
                    df_existing = pd.DataFrame(existing_data)

                    # Normalize existing columns too
                    df_existing.columns = [col.strip().lower().replace(' ', '_') for col in df_existing.columns]

                    # Merge: uploaded file has priority (updates/adds rows by sensor_id)
                    # Keep all columns from both datasets
                    df_merged = pd.concat([df_existing, df_uploaded], ignore_index=True)

                    # Remove duplicates, keeping the last (uploaded) version
                    df_merged = df_merged.drop_duplicates(subset=['sensor_id'], keep='last')

                    logger.info(f"Merged metadata: {len(df_existing)} from dataset + {len(df_uploaded)} uploaded = {len(df_merged)} total")
                else:
                    df_merged = df_uploaded
                    logger.info(f"Using uploaded metadata: {len(df_merged)} rows")

                # Ensure all expected columns exist (same as manual wizard)
                expected_columns = METADATA_SCHEMAS["metadata"]["columns"]
                df_merged = df_merged.reindex(columns=expected_columns)

                # Replace NaN with None
                df_merged = df_merged.where(pd.notna(df_merged), None)
                metadata_data = df_merged.to_dict('records')

                validation_results["metadata"] = {
                    "valid": True,
                    "rows": len(metadata_data),
                    "columns": list(df_merged.columns)
                }

                # Save merged result
                with open(metadata_path, 'w') as f:
                    json.dump(metadata_data, f, indent=2)

                config_summary["metadata"] = True

            except ValidationError as e:
                raise HTTPException(status_code=400, detail=f"Metadata validation failed: {str(e)}")

        # 2. QC params file (merges with or overrides dataset config)
        # Load existing qc_config from dataset copy if it exists
        qc_config_path = session_dir / "config_qc.json"
        if qc_config_path.exists():
            with open(qc_config_path) as f:
                qc_config_data = json.load(f)
            logger.info("Loaded existing QC config from dataset")
        else:
            qc_config_data = {
                "qc_cfg": {},
                "correction_table": [],
                "calibration_table": [],
                "field_events": []
            }

        if qc_params_file:
            try:
                validation = await validate_qc_params_file(qc_params_file)
                validation_results["qc_params"] = validation

                # Parse and merge into qc_config_data
                await qc_params_file.seek(0)
                content = await qc_params_file.read()
                qc_data = json.loads(content.decode("utf-8"))

                qc_config_data["qc_cfg"] = qc_data.get("qc_cfg", {})

                # Optional tables from QC file
                if "correction_table" in qc_data:
                    qc_config_data["correction_table"] = qc_data["correction_table"]
                if "calibration_table" in qc_data:
                    qc_config_data["calibration_table"] = qc_data["calibration_table"]
                if "field_events" in qc_data:
                    qc_config_data["field_events"] = qc_data["field_events"]

                config_summary["qc_params"] = True
                logger.info("Saved QC params")

            except ValidationError as e:
                raise HTTPException(status_code=400, detail=f"QC params validation failed: {str(e)}")

        # 3. Corrections file (merges with dataset corrections)
        if corrections_file:
            try:
                # Read and parse uploaded file
                content = await corrections_file.read()

                import pandas as pd
                import io
                df_uploaded = pd.read_csv(io.BytesIO(content))

                # Apply column mapping (rename columns from user mapping)
                if corrections_col_mapping:
                    # Reverse mapping: actualColumn -> expectedColumn
                    reverse_mapping = {v: k for k, v in corrections_col_mapping.items()}
                    df_uploaded.rename(columns=reverse_mapping, inplace=True)

                # Normalize column names (case-insensitive, trim whitespace)
                df_uploaded.columns = [col.strip().lower().replace(' ', '_') for col in df_uploaded.columns]

                # Validate AFTER mapping and normalization
                required_cols = ['sensor_id', 'correction_type', 'factor_a']
                missing = [col for col in required_cols if col not in df_uploaded.columns]
                if missing:
                    raise ValidationError(f"Missing required columns: {', '.join(missing)}")

                # Merge with existing corrections from dataset (if they exist)
                if qc_config_data.get("correction_table"):
                    df_existing = pd.DataFrame(qc_config_data["correction_table"])
                    df_existing.columns = [col.strip().lower().replace(' ', '_') for col in df_existing.columns]

                    # Merge: uploaded file has priority (updates/adds rows by sensor_id + correction_type)
                    df_merged = pd.concat([df_existing, df_uploaded], ignore_index=True)
                    df_merged = df_merged.drop_duplicates(subset=['sensor_id', 'correction_type'], keep='last')

                    logger.info(f"Merged corrections: {len(df_existing)} from dataset + {len(df_uploaded)} uploaded = {len(df_merged)} total")
                else:
                    df_merged = df_uploaded
                    logger.info(f"Using uploaded corrections: {len(df_merged)} rules")

                # Ensure all expected columns exist (same as manual wizard)
                expected_cols = METADATA_SCHEMAS["correction"]["columns"]
                df_merged = df_merged.reindex(columns=expected_cols)

                df_merged = df_merged.where(pd.notna(df_merged), None)
                qc_config_data["correction_table"] = df_merged.to_dict('records')

                validation_results["corrections"] = {
                    "valid": True,
                    "rows": len(df_merged),
                    "columns": list(df_merged.columns)
                }

                config_summary["corrections"] = True

            except ValidationError as e:
                raise HTTPException(status_code=400, detail=f"Corrections validation failed: {str(e)}")

        # 4. Calibrations file (merges with dataset calibrations)
        if calibrations_file:
            try:
                # Read and parse uploaded file
                content = await calibrations_file.read()

                import pandas as pd
                import io
                df_uploaded = pd.read_csv(io.BytesIO(content))

                # Apply column mapping (rename columns from user mapping)
                if calibrations_col_mapping:
                    # Reverse mapping: actualColumn -> expectedColumn
                    reverse_mapping = {v: k for k, v in calibrations_col_mapping.items()}
                    df_uploaded.rename(columns=reverse_mapping, inplace=True)

                # Normalize column names (case-insensitive, trim whitespace)
                df_uploaded.columns = [col.strip().lower().replace(' ', '_') for col in df_uploaded.columns]

                # Validate AFTER mapping and normalization
                if 'sensor_id' not in df_uploaded.columns:
                    raise ValidationError("Missing required column: 'sensor_id'")

                # Merge with existing calibrations from dataset (if they exist)
                if qc_config_data.get("calibration_table"):
                    df_existing = pd.DataFrame(qc_config_data["calibration_table"])
                    df_existing.columns = [col.strip().lower().replace(' ', '_') for col in df_existing.columns]

                    # Merge: uploaded file has priority (updates/adds rows by sensor_id)
                    df_merged = pd.concat([df_existing, df_uploaded], ignore_index=True)
                    df_merged = df_merged.drop_duplicates(subset=['sensor_id'], keep='last')

                    logger.info(f"Merged calibrations: {len(df_existing)} from dataset + {len(df_uploaded)} uploaded = {len(df_merged)} total")
                else:
                    df_merged = df_uploaded
                    logger.info(f"Using uploaded calibrations: {len(df_merged)} rules")

                # Ensure all expected columns exist (same as manual wizard)
                expected_cols = METADATA_SCHEMAS["calibration"]["columns"]
                df_merged = df_merged.reindex(columns=expected_cols)

                df_merged = df_merged.where(pd.notna(df_merged), None)
                qc_config_data["calibration_table"] = df_merged.to_dict('records')

                validation_results["calibrations"] = {
                    "valid": True,
                    "rows": len(df_merged),
                    "columns": list(df_merged.columns)
                }

                config_summary["calibrations"] = True

            except ValidationError as e:
                raise HTTPException(status_code=400, detail=f"Calibrations validation failed: {str(e)}")

        # Save unified QC config file (always save to persist dataset config + manual uploads)
        if qc_config_data["qc_cfg"] or qc_config_data["correction_table"] or qc_config_data["calibration_table"] or qc_config_data["field_events"]:
            qc_config_path = session_dir / "config_qc.json"
            with open(qc_config_path, 'w') as f:
                json.dump(qc_config_data, f, indent=2)
            logger.info("Saved unified QC config (dataset + manual uploads)")

        # Initialize status.json
        status_data = {
            "status": "queued",
            "current_stage": None,
            "error_message": None,
            "started_at": None,
            "last_updated": None
        }
        status_file = session_dir / "status.json"
        with open(status_file, 'w') as f:
            json.dump(status_data, f, indent=2)

        # Enqueue automated pipeline job
        job = default_queue.enqueue(
            tasks.run_automated_tms_pipeline,
            session_id=session_id,
            pipeline_type=pipeline_type,
            job_timeout='60m',
            result_ttl=86400,
            failure_ttl=3600,
            meta={
                'session_id': session_id,
                'pipeline_type': pipeline_type,
                'progress': 0,
                'current_stage': 'queued',
                'message': 'Automated pipeline queued'
            }
        )

        logger.info(f"Enqueued automated pipeline job {job.id} for session {session_id}")

        return {
            "session_id": session_id,
            "pipeline_type": pipeline_type,
            "user": user,
            "job_id": job.id,
            "status": "queued",
            "files": uploaded_files,
            "total_files": len(uploaded_files),
            "config_source": "dataset" if source_dataset_id else "uploaded",
            "config_summary": config_summary
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create automated session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{session_id}/run-stage/{stage_name}")
async def run_session_stage(
    session_id: str,
    stage_name: str,
    pipeline_type: str = "tms"
):
    """Trigger a job to compute a specific pipeline stage for a session.

    This allows the wizard to run stages on-demand as the user progresses
    through the steps, instead of running the entire pipeline upfront.
    """
    try:
        from backend.workers.connection import default_queue
        from backend.workers import tasks

        session_dir = store.session_dir(session_id, pipeline_type)
        if not session_dir.exists():
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        # Enqueue RQ job
        job = default_queue.enqueue(
            tasks.run_session_stage,
            session_id=session_id,
            stage_name=stage_name,
            pipeline_type=pipeline_type,
            job_timeout='30m',
            result_ttl=86400,
            failure_ttl=3600,
            meta={
                'session_id': session_id,
                'pipeline_type': pipeline_type,
                'stage_name': stage_name,
                'progress': 0,
                'current_stage': stage_name,
                'message': f'Computing {stage_name}'
            }
        )

        logger.info(f"Enqueued stage job {job.id} for session {session_id}, stage {stage_name}")

        return {
            "job_id": job.id,
            "session_id": session_id,
            "stage_name": stage_name,
            "pipeline_type": pipeline_type,
            "status": "queued"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to run stage {stage_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/stages")
async def list_session_stages(
    session_id: str,
    pipeline_type: str = Query(..., description="Pipeline type (tms)")
):
    """List all available stages for a session.

    Returns which pipeline stages have been computed and are available
    as Parquet files on disk.
    """
    try:
        session_dir = store.session_dir(session_id, pipeline_type)

        if not session_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )

        # Find all .parquet files (excluding hash manifests)
        stage_files = list(session_dir.glob("*.parquet"))

        # Build stage info
        stages = []
        for file_path in sorted(stage_files):
            # Skip duplicate report files and similar auxiliaries
            stage_name = file_path.stem
            if "__" in stage_name:
                # Handle multi-output stages like "merged__dup_report"
                base_name = stage_name.split("__")[0]
                output_name = stage_name.split("__")[1]
                stage_key = stage_name
            else:
                base_name = stage_name
                output_name = "main"
                stage_key = stage_name

            file_size = file_path.stat().st_size

            stages.append({
                "stage": stage_key,
                "base_name": base_name,
                "output_name": output_name,
                "file_path": str(file_path),
                "file_size": file_size,
                "available": True
            })

        # Map to human-readable labels (TMS stage order)
        stage_order = [
            "merged", "with_metadata", "initial_qc",
            "corrected", "calibrated", "final", "production"
        ]
        stage_labels = {
            "merged": "Loading & Continuity",
            "with_metadata": "Metadata",
            "initial_qc": "Initial QC",
            "corrected": "Signal Correction",
            "calibrated": "VWC Calibration",
            "final": "Final QC",
            "production": "Production Dataset"
        }

        # Add labels and order
        for stage_info in stages:
            base = stage_info["base_name"]
            stage_info["label"] = stage_labels.get(base, base.replace("_", " ").title())
            stage_info["order"] = stage_order.index(base) if base in stage_order else 999

        return {
            "session_id": session_id,
            "pipeline_type": pipeline_type,
            "stages": sorted(stages, key=lambda x: x["order"]),
            "total_stages": len(stages)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list stages for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/stages/{stage_name}")
async def get_stage_data(
    session_id: str,
    stage_name: str,
    pipeline_type: str = Query(..., description="Pipeline type (tms)"),
    limit: int = Query(1000, ge=1, le=10000, description="Max rows to sample"),
    columns: Optional[str] = Query(None, description="Comma-separated column names")
):
    """Get data for a specific pipeline stage.

    Returns sampled data from the stage's Parquet file for visualization.
    Uses even sampling to preserve temporal distribution.
    """
    try:
        session_dir = store.session_dir(session_id, pipeline_type)

        # Handle multi-output stages (e.g., "merged__dup_report")
        stage_file = session_dir / f"{stage_name}.parquet"

        if not stage_file.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Stage '{stage_name}' not found for session {session_id}"
            )

        # Read with DuckDB for efficient sampling
        import duckdb
        con = duckdb.connect()

        # Parse requested columns
        col_list = None
        if columns:
            col_list = [c.strip() for c in columns.split(",")]

        # Get total row count
        count_query = build_stage_count_query(str(stage_file))
        total_rows = con.execute(count_query).fetchone()[0]

        # Handle empty or very small files
        if total_rows == 0:
            # Return empty dataframe with schema
            schema_query = build_empty_schema_query(str(stage_file), col_list)
            df = con.execute(schema_query).df()
            con.close()
        else:
            # Sample evenly
            sample_size = min(limit, total_rows)
            sample_query = build_stage_sample_query(
                str(stage_file), col_list, sample_size, total_rows
            )

            df = con.execute(sample_query).df()
            con.close()

        # Convert to JSON-friendly format
        # Replace NaN/NaT with None
        import numpy as np
        df = df.replace({np.nan: None})

        # Convert timestamps to strings
        for col in df.select_dtypes(include=['datetime64']).columns:
            df[col] = df[col].astype(str)

        result = {
            "session_id": session_id,
            "stage": stage_name,
            "pipeline_type": pipeline_type,
            "total_rows": total_rows,
            "sampled_rows": len(df),
            "columns": list(df.columns),
            "data": df.to_dict('records')
        }

        logger.info(f"Returning {len(df)} rows for stage {stage_name} (from {total_rows} total)")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get stage data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/status")
async def get_session_status(
    session_id: str,
    pipeline_type: str = Query("tms", description="Pipeline type (tms)")
):
    """Get current status of a session (for automated runs).

    Returns the status from status.json if it exists, otherwise infers
    status from available stages.

    Status values:
    - "processing": Automated run in progress
    - "needs_attention": Automated run failed, manual intervention required
    - "completed": Automated run completed successfully
    - "manual": No automated run, user is using wizard manually
    """
    try:
        session_dir = store.session_dir(session_id, pipeline_type)

        if not session_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )

        status_file = session_dir / "status.json"

        # If status.json exists, return it (automated run)
        if status_file.exists():
            try:
                with open(status_file) as f:
                    status_data = json.load(f)

                return {
                    "session_id": session_id,
                    "pipeline_type": pipeline_type,
                    **status_data
                }
            except (json.JSONDecodeError, ValueError):
                # Empty or malformed status.json, fall through to infer from stages
                logger.warning(f"Malformed status.json for session {session_id}, inferring from stages")
                pass

        # Otherwise, infer status from available stages (manual wizard)
        stage_files = list(session_dir.glob("*.parquet"))
        available_stages = [f.stem.split("__")[0] for f in stage_files]

        # Determine current stage based on what exists (TMS stage order)
        stage_order = [
            "merged", "with_metadata", "initial_qc",
            "corrected", "calibrated", "final", "production"
        ]

        # Find highest completed stage
        current_stage = None
        for stage in reversed(stage_order):
            if stage in available_stages:
                current_stage = stage
                break

        # Calculate progress percentage
        if current_stage:
            stage_index = stage_order.index(current_stage)
            progress = int(((stage_index + 1) / len(stage_order)) * 100)
        else:
            current_stage = "loading"
            progress = 0

        return {
            "session_id": session_id,
            "pipeline_type": pipeline_type,
            "status": "manual",  # User is using wizard manually
            "current_stage": current_stage,
            "completed_stages": available_stages,
            "progress": progress,
            "error_message": None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
