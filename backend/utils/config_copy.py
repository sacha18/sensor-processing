"""Utilities for copying configuration from published datasets to new sessions."""
import json
import logging
from pathlib import Path
from typing import Dict, Any
from uuid import UUID

from backend.api.services import metadata as metadata_service
from backend.pipeline import store

logger = logging.getLogger(__name__)


async def copy_config_from_dataset(dataset_id: UUID, target_session_id: str, pipeline_type: str = "tms") -> Dict[str, Any]:
    """
    Copy all configuration from a published dataset to a target session.

    Args:
        dataset_id: UUID of the source dataset
        target_session_id: ID of the target session to copy config to
        pipeline_type: Pipeline type (default: tms)

    Returns:
        Dict with summary of copied configuration

    Raises:
        ValueError: If dataset not found or session directory doesn't exist
    """
    # Get dataset
    dataset = metadata_service.get_dataset_by_id(dataset_id)
    if not dataset:
        raise ValueError(f"Dataset {dataset_id} not found")

    # Verify session exists
    session_dir = store.session_dir(target_session_id, pipeline_type)
    if not session_dir.exists():
        raise ValueError(f"Session {target_session_id} not found")

    logger.info(f"Copying config from dataset {dataset_id} to session {target_session_id}")

    copied = {
        "metadata": False,
        "qc_config": False,
        "corrections": False,
        "calibrations": False,
        "field_events": False
    }

    # 1. Copy metadata table
    if dataset.get("metadata_table"):
        metadata_file = session_dir / "config_metadata.json"
        metadata_data = json.loads(dataset["metadata_table"]) if isinstance(dataset["metadata_table"], str) else dataset["metadata_table"]

        if metadata_data:
            with open(metadata_file, 'w') as f:
                json.dump(metadata_data, f, indent=2)
            copied["metadata"] = True
            logger.info(f"Copied {len(metadata_data)} metadata row(s)")

    # 2. Copy QC config + correction + calibration + field_events
    # All stored in config_qc.json
    config_data = {
        "qc_cfg": {},
        "correction_table": [],
        "calibration_table": [],
        "field_events": []
    }

    # QC config
    if dataset.get("config"):
        config_raw = json.loads(dataset["config"]) if isinstance(dataset["config"], str) else dataset["config"]
        if isinstance(config_raw, dict) and "qc_cfg" in config_raw:
            config_data["qc_cfg"] = config_raw["qc_cfg"]
            copied["qc_config"] = True
            logger.info("Copied QC config")

        # Field events might be in config too
        if isinstance(config_raw, dict) and "field_events" in config_raw:
            config_data["field_events"] = config_raw["field_events"]
            copied["field_events"] = True

    # Correction table
    if dataset.get("correction_table"):
        correction_data = json.loads(dataset["correction_table"]) if isinstance(dataset["correction_table"], str) else dataset["correction_table"]
        if correction_data:
            config_data["correction_table"] = correction_data
            copied["corrections"] = True
            logger.info(f"Copied {len(correction_data)} correction rule(s)")

    # Calibration table
    if dataset.get("calibration_table"):
        calibration_data = json.loads(dataset["calibration_table"]) if isinstance(dataset["calibration_table"], str) else dataset["calibration_table"]
        if calibration_data:
            config_data["calibration_table"] = calibration_data
            copied["calibrations"] = True
            logger.info(f"Copied {len(calibration_data)} calibration rule(s)")

    # Save QC config file (unified config)
    if copied["qc_config"] or copied["corrections"] or copied["calibrations"] or copied["field_events"]:
        qc_config_file = session_dir / "config_qc.json"
        with open(qc_config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
        logger.info("Saved unified QC config file")

    # Log summary
    copied_items = [k for k, v in copied.items() if v]
    logger.info(f"Successfully copied config from dataset {dataset_id}: {', '.join(copied_items)}")

    return {
        "success": True,
        "source_dataset_id": str(dataset_id),
        "source_dataset_title": dataset.get("title", "Unknown"),
        "target_session_id": target_session_id,
        "copied": copied,
        "message": f"Copied {len(copied_items)} configuration component(s)"
    }
