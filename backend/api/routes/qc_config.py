"""API routes for QC configuration management."""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from pathlib import Path
import logging
import json

from backend.pipeline import store

router = APIRouter(prefix="/api/sessions", tags=["qc_config"])
logger = logging.getLogger(__name__)


def default_qc_cfg() -> Dict[str, Any]:
    """Return default QC configuration for all channels."""
    default_channel_cfg = {
        "use_hampel": True,
        "hampel_k": 3.0,
        "hampel_half_window": 5,
        "use_flatline": True,
        "flatline_min_run": 50,
        "use_percentile": False,
        "pct_low": 0,
        "pct_high": 100,
        "use_rate": True,
        "rate_k": 10.0,
    }
    return {
        "t1": default_channel_cfg.copy(),
        "t2": default_channel_cfg.copy(),
        "t3": default_channel_cfg.copy(),
        "signal": default_channel_cfg.copy(),
    }


def _get_qc_config_file(session_id: str, pipeline_type: str) -> Path:
    """Get path to QC config JSON file for a session."""
    session_dir = store.session_dir(session_id, pipeline_type)
    return session_dir / "config_qc.json"


@router.get("/{session_id}/qc-config/{pipeline_type}")
async def get_qc_config(session_id: str, pipeline_type: str = "tms"):
    """Get QC configuration for a session (includes qc_cfg, correction_table, calibration_table, field_events)."""
    if pipeline_type != "tms":
        raise HTTPException(status_code=400, detail="QC config only supported for TMS pipeline")

    session_dir = store.session_dir(session_id, pipeline_type)
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    qc_config_file = _get_qc_config_file(session_id, pipeline_type)

    # Return default config if file doesn't exist
    if not qc_config_file.exists():
        return {
            "qc_cfg": default_qc_cfg(),
            "correction_table": [],
            "calibration_table": [],
            "field_events": []
        }

    try:
        with open(qc_config_file, 'r') as f:
            config = json.load(f)
        # Ensure all fields exist for backwards compatibility
        if "correction_table" not in config:
            config["correction_table"] = []
        if "calibration_table" not in config:
            config["calibration_table"] = []
        if "field_events" not in config:
            config["field_events"] = []
        return config
    except Exception as e:
        logger.error(f"Failed to load QC config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load QC config: {e}")


@router.put("/{session_id}/qc-config/{pipeline_type}")
async def update_qc_config(
    session_id: str,
    config: Dict[str, Any],
    pipeline_type: str = "tms"
):
    """Update QC configuration for a session (supports qc_cfg, correction_table, calibration_table, field_events)."""
    if pipeline_type != "tms":
        raise HTTPException(status_code=400, detail="QC config only supported for TMS pipeline")

    session_dir = store.session_dir(session_id, pipeline_type)
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    qc_config_file = _get_qc_config_file(session_id, pipeline_type)

    try:
        # Validate structure - must have qc_cfg with channel keys
        if "qc_cfg" not in config:
            raise ValueError("Config must have 'qc_cfg' key")

        qc_cfg = config["qc_cfg"]
        expected_channels = ["t1", "t2", "t3", "signal"]

        for channel in expected_channels:
            if channel not in qc_cfg:
                raise ValueError(f"Missing channel config for {channel}")

        # Optional: validate correction_table, calibration_table, field_events structure
        # For now just ensure they're lists if present
        if "correction_table" in config and not isinstance(config["correction_table"], list):
            raise ValueError("correction_table must be a list")
        if "calibration_table" in config and not isinstance(config["calibration_table"], list):
            raise ValueError("calibration_table must be a list")
        if "field_events" in config and not isinstance(config["field_events"], list):
            raise ValueError("field_events must be a list")

        # Save to file
        with open(qc_config_file, 'w') as f:
            json.dump(config, f, indent=2)

        return {"success": True, "message": "QC config updated"}
    except Exception as e:
        logger.error(f"Failed to save QC config: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to save QC config: {e}")
