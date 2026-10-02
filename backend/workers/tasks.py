"""RQ tasks for running sensor data pipelines.

These tasks are enqueued by the FastAPI backend and executed by RQ workers.
They reuse the existing pipeline/* code (currently just TMS orchestration).

Adding a new pipeline here means writing a new `run_<name>_pipeline` job
function, same shape as `run_tms_pipeline` below, reusing the two helpers
this module already provides: `_make_progress_callback` (stage-label -> job
progress %) and `_records_to_df` (uploaded-config-table JSON -> DataFrame
with the right datetime columns parsed) - rather than re-deriving them.
"""
from rq import get_current_job
import logging
from pathlib import Path
from typing import Optional
import pandas as pd

# Import existing pipeline orchestration
import backend.pipeline.tms as TMS
from backend.pipeline import store

logger = logging.getLogger(__name__)

TMS_STAGES = ["merged", "gap_report", "with_metadata", "initial_qc", "corrected", "calibrated", "final", "production"]


def _make_progress_callback(job, stages: list[str]):
    """Builds the `progress(stage_label)` callback `process_pipeline()`/
    `process_tms_pipeline()` call right before a stage that's actually
    recomputing (never on a cache hit). Maps the human-readable label back
    to its position in `stages` (matched by a 4-char prefix, since labels are
    free text like "Deduplicating readings" for stage key "deduped") to
    compute a 0-100% figure, then publishes it on the RQ job's metadata so
    the API can relay it to the frontend."""
    def progress_callback(stage_label: str):
        stage_key = next((s for s in stages if stage_label.lower().startswith(s[:4])), None)
        progress_pct = int((stages.index(stage_key) / len(stages)) * 100) if stage_key else 50

        job.meta['progress'] = progress_pct
        job.meta['current_stage'] = stage_label
        job.meta['message'] = f"Computing {stage_label}..."
        job.save_meta()

        logger.info(f"[Job {job.id}] {progress_pct}% - {stage_label}")

    return progress_callback


def _records_to_df(records: Optional[list], datetime_cols: tuple[str, ...] = ()) -> pd.DataFrame:
    """Turns a JSON-decoded list of row-dicts (an uploaded/stored config
    table - metadata, correction, calibration, field_events) into a
    DataFrame, parsing `datetime_cols` that are present (DuckDB's bind-time
    type checks need real timestamps, not strings, once this flows into a
    pipeline SQL query). Empty/None input -> empty DataFrame, same as the
    pipeline functions already expect for "no config table supplied"."""
    df = pd.DataFrame(records or [])
    if not df.empty:
        for col in datetime_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
    return df


class _DiskUploadedFile:
    """Simple file-like object that reads from disk, mimicking the upload interface pipeline/*/io.py expects."""
    def __init__(self, path: Path):
        self.path = path
        self.name = path.name

    def getvalue(self):
        return self.path.read_bytes()

    def read(self):
        return self.path.read_bytes()


def run_tms_pipeline(
    session_id: str,
    raw_files: list[str],
    config: dict,
    user: str = None
) -> dict:
    """RQ job: Execute the TOMST TMS-4 soil sensor pipeline.

    Args:
        session_id: Unique session identifier
        raw_files: List of uploaded TOMST binary file paths
        config: Pipeline configuration dict with keys:
            - metadata_df: pd.DataFrame (deployment metadata)
            - correction_params: pd.DataFrame
            - calibration_params: pd.DataFrame
            - field_events: Optional[pd.DataFrame]
            - qc_cfg: dict (initial QC params)
            - final_qc_cfg: dict
            - step_min: Optional[int]
        user: Optional user email/name

    Returns:
        dict with status, session_id, stage paths
    """
    job = get_current_job()
    logger.info(f"[Job {job.id}] Starting TMS pipeline for session {session_id}")

    progress_callback = _make_progress_callback(job, TMS_STAGES)

    try:
        pipeline_dir = store.session_dir(session_id, "tms")

        # Parse uploaded TOMST files
        uploads_dir = pipeline_dir / "uploads"
        raw_output_dir = pipeline_dir / "raw"

        upload_files = list(uploads_dir.glob("*.csv")) + list(uploads_dir.glob("*.TMS")) + list(uploads_dir.glob("*.xlsx"))

        if not upload_files:
            raise ValueError("No TOMST files found in uploads directory")

        logger.info(f"[Job {job.id}] Found {len(upload_files)} upload files")

        # Convert uploaded files to file-like objects
        file_objects = [_DiskUploadedFile(p) for p in upload_files]

        # Convert TOMST files to Parquet (handles .csv raw exports and .xlsx metadata)
        raw_paths, failures = TMS.write_tms_raw_uploads_to_store(file_objects, raw_output_dir)

        if failures:
            logger.warning(f"[Job {job.id}] {len(failures)} files failed to parse: {failures}")

        if not raw_paths:
            raise ValueError(f"No valid TOMST files could be parsed. Failures: {failures}")

        logger.info(f"[Job {job.id}] Created {len(raw_paths)} Parquet files")

        # Convert config tables from JSON back to DataFrames
        metadata_df = _records_to_df(config.get("metadata_table"), ('install_start', 'install_end'))
        correction_params = _records_to_df(config.get("correction_table"), ('valid_from', 'valid_to'))
        calibration_params = _records_to_df(config.get("calibration_table"), ('valid_from', 'valid_to'))
        field_events = _records_to_df(config.get("field_events"), ('start', 'end', 'created_at')) if config.get("field_events") else None

        # Run TMS pipeline orchestration
        result = TMS.process_tms_pipeline(
            pipeline_dir=pipeline_dir,
            raw_paths=raw_paths,
            metadata_df=metadata_df,
            correction_params=correction_params,
            calibration_params=calibration_params,
            field_events=field_events,
            qc_cfg=config.get("qc_cfg", {}),
            final_qc_cfg=config.get("final_qc_cfg", {}),
            step_min=config.get("step_min"),
            progress=progress_callback
        )

        # Force evaluation of production stage (LazyDict only computes when accessed)
        production_path = result["production"]
        logger.info(f"[Job {job.id}] Production file created: {production_path}")

        job.meta['progress'] = 100
        job.meta['message'] = "Pipeline completed successfully"
        job.meta['current_stage'] = "complete"
        job.save_meta()

        logger.info(f"[Job {job.id}] TMS pipeline completed for session {session_id}")

        return {
            "status": "completed",
            "session_id": session_id,
            "pipeline_type": "tms",
            "stages": list(result.keys()),
            "production_path": str(production_path),
            "user": user
        }

    except Exception as e:
        logger.error(f"[Job {job.id}] TMS pipeline failed: {e}", exc_info=True)
        job.meta['error'] = str(e)
        job.meta['progress'] = 0
        job.save_meta()
        raise


def run_session_stage(
    session_id: str,
    stage_name: str,
    pipeline_type: str = "tms"
) -> dict:
    """RQ job: Compute a specific pipeline stage for a session.

    This is used by the wizard to run stages on-demand. The stage's
    dependencies will be computed automatically if not already cached.

    Args:
        session_id: Session identifier
        stage_name: Stage to compute (e.g., "merged", "with_metadata", "initial_qc")
        pipeline_type: "tms" (the only pipeline with on-demand stage runs)

    Returns:
        dict with status, session_id, stage info
    """
    job = get_current_job()
    logger.info(f"[Job {job.id}] Running stage {stage_name} for session {session_id}")

    def progress_callback(label: str):
        job.meta['current_stage'] = label
        job.meta['message'] = f"Computing {label}..."
        job.save_meta()
        logger.info(f"[Job {job.id}] {label}")

    try:
        pipeline_dir = store.session_dir(session_id, pipeline_type)

        if pipeline_type == "tms":
            # Load files from uploads
            uploads_dir = pipeline_dir / "uploads"
            raw_output_dir = pipeline_dir / "raw"

            # Convert uploads to Parquet if not already done
            raw_parquet_dir = pipeline_dir / "raw"
            if not list(raw_parquet_dir.glob("*.parquet")):
                upload_files = list(uploads_dir.glob("*.csv")) + list(uploads_dir.glob("*.TMS"))
                if not upload_files:
                    raise ValueError("No TOMST files found in uploads")

                file_objects = [_DiskUploadedFile(p) for p in upload_files]
                raw_paths, failures = TMS.write_tms_raw_uploads_to_store(file_objects, raw_output_dir)

                if failures:
                    logger.warning(f"[Job {job.id}] {len(failures)} files failed: {failures}")
                if not raw_paths:
                    raise ValueError(f"No valid files parsed. Failures: {failures}")
            else:
                raw_paths = list(raw_parquet_dir.glob("*.parquet"))

            logger.info(f"[Job {job.id}] Using {len(raw_paths)} raw Parquet files")

            # Load metadata config if exists
            metadata_file = pipeline_dir / "config_metadata.json"
            if metadata_file.exists():
                import json
                with open(metadata_file) as f:
                    metadata_df = _records_to_df(json.load(f), ('install_start', 'install_end'))
            else:
                metadata_df = pd.DataFrame()

            # Load QC config if exists (includes qc_cfg, correction_table, calibration_table, field_events)
            qc_config_file = pipeline_dir / "config_qc.json"
            if qc_config_file.exists():
                import json
                with open(qc_config_file) as f:
                    qc_config = json.load(f)
                    qc_cfg = qc_config.get("qc_cfg", {})
                    correction_params = _records_to_df(qc_config.get("correction_table"), ('valid_from', 'valid_to'))
                    calibration_params = _records_to_df(qc_config.get("calibration_table"), ('valid_from', 'valid_to'))
                    field_events = _records_to_df(qc_config.get("field_events"), ('start', 'end', 'created_at')) if qc_config.get("field_events") else None
            else:
                qc_cfg = {}
                correction_params = pd.DataFrame()
                calibration_params = pd.DataFrame()
                field_events = None

            # Run orchestration - only the requested stage will be computed
            result = TMS.process_tms_pipeline(
                pipeline_dir=pipeline_dir,
                raw_paths=raw_paths,
                metadata_df=metadata_df,
                correction_params=correction_params,
                calibration_params=calibration_params,
                field_events=field_events,
                qc_cfg=qc_cfg,  # Use custom config if loaded
                final_qc_cfg={},
                step_min=None,
                progress=progress_callback
            )

            # Access the requested stage - this triggers computation
            stage_map = {
                "merged": "merged",
                "merged__dup_report": "dup_report",
                "gap_report": "gap_report",
                "with_metadata": "with_metadata",
                "excluded_metadata": "excluded_metadata",
                "initial_qc": "qc",
                "corrected": "corrected",
                "calibrated": "calibrated",
                "final": "final",
                "production": "production",
            }

            result_key = stage_map.get(stage_name, stage_name)
            stage_path = result[result_key]

            logger.info(f"[Job {job.id}] Stage {stage_name} computed: {stage_path}")

        else:
            raise ValueError(f"Pipeline type {pipeline_type} not yet supported for stage runs")

        job.meta['progress'] = 100
        job.meta['message'] = f"Stage {stage_name} completed"
        job.save_meta()

        return {
            "status": "completed",
            "session_id": session_id,
            "pipeline_type": pipeline_type,
            "stage_name": stage_name,
            "stage_path": str(stage_path)
        }

    except Exception as e:
        logger.error(f"[Job {job.id}] Stage {stage_name} failed: {e}", exc_info=True)
        job.meta['error'] = str(e)
        job.meta['progress'] = 0
        job.save_meta()
        raise


def run_automated_tms_pipeline(
    session_id: str,
    pipeline_type: str = "tms"
) -> dict:
    """RQ job: Execute all TMS pipeline stages automatically in sequence.

    This function runs all stages from merged to production automatically,
    stopping if any stage fails. The session status is tracked in status.json.

    Args:
        session_id: Session identifier
        pipeline_type: Pipeline type (default: "tms")

    Returns:
        dict with completion status and any errors
    """
    job = get_current_job()
    logger.info(f"[Job {job.id}] Starting automated TMS pipeline for session {session_id}")

    STAGES = TMS_STAGES

    pipeline_dir = store.session_dir(session_id, pipeline_type)
    status_file = pipeline_dir / "status.json"

    def _update_status(status: str, current_stage: str = None, error: str = None, completed: list = None):
        """Update session status.json file."""
        import json
        from datetime import datetime

        status_data = {
            "status": status,
            "current_stage": current_stage,
            "error_message": error,
            "completed_stages": completed or [],
            "last_updated": datetime.utcnow().isoformat()
        }

        # Load existing status to preserve started_at
        if status_file.exists():
            with open(status_file) as f:
                existing = json.load(f)
                if "started_at" in existing:
                    status_data["started_at"] = existing["started_at"]

        # Add started_at if this is the first update
        if "started_at" not in status_data:
            status_data["started_at"] = datetime.utcnow().isoformat()

        # Calculate progress
        if status == "completed":
            # Completed runs should always show 100%
            progress = 100
        elif completed:
            progress = int((len(completed) / len(STAGES)) * 100)
        else:
            progress = 0
        status_data["progress"] = progress

        with open(status_file, 'w') as f:
            json.dump(status_data, f, indent=2)

        logger.info(f"[Job {job.id}] Updated status: {status}, stage: {current_stage}, completed: {len(completed or [])}/{len(STAGES)}")

    try:
        # Initialize status
        _update_status("processing", current_stage="merged", completed=[])

        completed_stages = []

        for i, stage_name in enumerate(STAGES):
            # Update progress
            progress_pct = int((i / len(STAGES)) * 100)
            job.meta['progress'] = progress_pct
            job.meta['current_stage'] = stage_name
            job.meta['message'] = f"Running {stage_name}..."
            job.save_meta()

            logger.info(f"[Job {job.id}] Running stage {i+1}/{len(STAGES)}: {stage_name}")

            try:
                # Run the stage using existing function
                stage_result = run_session_stage(
                    session_id=session_id,
                    stage_name=stage_name,
                    pipeline_type=pipeline_type
                )

                completed_stages.append(stage_name)
                logger.info(f"[Job {job.id}] Stage {stage_name} completed successfully")

                # Update status file
                _update_status("processing", current_stage=stage_name, completed=completed_stages)

            except Exception as stage_error:
                # Stage failed - mark session as needs_attention
                error_msg = f"Failed at stage '{stage_name}': {str(stage_error)}"
                logger.error(f"[Job {job.id}] {error_msg}", exc_info=True)

                _update_status("needs_attention", current_stage=stage_name, error=error_msg, completed=completed_stages)

                # Update job metadata
                job.meta['error'] = error_msg
                job.meta['failed_stage'] = stage_name
                job.meta['completed_stages'] = completed_stages
                job.save_meta()

                # Re-raise to mark RQ job as failed
                raise RuntimeError(error_msg) from stage_error

        # All stages completed successfully
        _update_status("completed", current_stage="production", completed=completed_stages)

        job.meta['progress'] = 100
        job.meta['message'] = "Automated pipeline completed successfully"
        job.meta['current_stage'] = "complete"
        job.meta['completed_stages'] = completed_stages
        job.save_meta()

        logger.info(f"[Job {job.id}] Automated TMS pipeline completed successfully for session {session_id}")

        return {
            "status": "completed",
            "session_id": session_id,
            "pipeline_type": pipeline_type,
            "completed_stages": completed_stages,
            "message": "All stages completed successfully"
        }

    except Exception as e:
        logger.error(f"[Job {job.id}] Automated pipeline failed: {e}", exc_info=True)
        # Status already updated in the stage error handler above
        # Just update job metadata
        job.meta['progress'] = 0
        job.save_meta()
        raise
