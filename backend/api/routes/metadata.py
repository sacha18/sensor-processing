"""API routes for session metadata management."""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional, List, Dict, Any
from pathlib import Path
import logging
import json
import pandas as pd
import io

from backend.pipeline import store

router = APIRouter(prefix="/api/sessions", tags=["metadata"])
logger = logging.getLogger(__name__)

# TOMST default labels for near-surface installation
NEAR_SURFACE_POSITION = "near-surface"
NEAR_SURFACE_LABELS = {
    "t1_label": "Air temp",
    "t2_label": "Surface temp",
    "t3_label": "Soil temp (-6cm)",
}

METADATA_SCHEMAS = {
    "metadata": {
        "columns": ["sensor_id", "group_key", "site", "treatment", "position", "position_depth",
                    "row", "transect", "depth_cm", "t1_label", "t2_label", "t3_label",
                    "install_start", "install_end", "notes"],
    },
    "correction": {
        "columns": ["sensor_id", "correction_type", "factor_a", "factor_b",
                    "valid_from", "valid_to", "notes"],
    },
    "calibration": {
        "columns": ["sensor_id", "coef_0", "coef_1", "coef_2", "coef_3", "coef_4", "coef_5",
                    "valid_from", "valid_to", "notes"],
    },
    "field_events": {
        "columns": ["sensor_id", "treatment", "channel", "start", "end", "event_type", "note",
                    "edit_id", "created_by", "created_at"],
    },
}


def _get_metadata_file(session_id: str, pipeline_type: str, table_name: str) -> Path:
    """Get path to metadata JSON file for a session."""
    session_dir = store.session_dir(session_id, pipeline_type)
    return session_dir / f"config_{table_name}.json"


def _normalize_dataframe(df: pd.DataFrame, table_name: str) -> List[Dict[str, Any]]:
    """Normalize DataFrame to JSON-serializable format."""
    # Convert datetime columns to ISO strings
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S').replace('NaT', None)

    # Replace NaN with None
    df = df.where(pd.notna(df), None)

    return df.to_dict(orient='records')


def _parse_uploaded_file(file: UploadFile, skiprows: int = 0) -> pd.DataFrame:
    """Parse uploaded CSV/JSON/XLSX file."""
    suffix = Path(file.filename).suffix.lower()
    content = file.file.read()

    if suffix == ".json":
        return pd.DataFrame(json.loads(content.decode("utf-8")))
    elif suffix == ".xlsx":
        return pd.read_excel(io.BytesIO(content), skiprows=skiprows)
    else:  # CSV
        return pd.read_csv(io.BytesIO(content), skiprows=skiprows)


@router.post("/{session_id}/metadata/{table_name}/seed")
async def seed_metadata_from_loaded_sensors(
    session_id: str,
    table_name: str = "metadata",
    pipeline_type: str = "tms"
):
    """Seed metadata table with sensors from loaded data."""
    if table_name != "metadata":
        raise HTTPException(status_code=400, detail="Only metadata table can be seeded")

    session_dir = store.session_dir(session_id, pipeline_type)
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    metadata_file = _get_metadata_file(session_id, pipeline_type, table_name)

    # Don't seed if metadata already exists
    if metadata_file.exists():
        with open(metadata_file, 'r') as f:
            existing_data = json.load(f)
            if existing_data:
                return {
                    "success": True,
                    "seeded": False,
                    "message": "Metadata already exists",
                    "rows": len(existing_data)
                }

    # Load merged data to get sensors
    merged_file = session_dir / "merged.parquet"
    if not merged_file.exists():
        raise HTTPException(status_code=404, detail="No merged data found - run pipeline first")

    try:
        merged_df = pd.read_parquet(merged_file)

        if merged_df.empty:
            return {
                "success": True,
                "seeded": False,
                "message": "No sensors found in merged data",
                "rows": 0
            }

        # Get first timestamp per sensor
        first_seen = merged_df.groupby(merged_df['sensor_id'].astype(str))['timestamp'].min()

        # Create seed data
        seed_data = []
        for sensor_id in sorted(first_seen.index):
            row = {
                'sensor_id': sensor_id,
                'group_key': None,
                'site': None,
                'treatment': None,
                'position': NEAR_SURFACE_POSITION,
                'position_depth': None,
                'row': None,
                'transect': None,
                'depth_cm': 14,  # Standard TOMST near-surface depth
                't1_label': NEAR_SURFACE_LABELS['t1_label'],
                't2_label': NEAR_SURFACE_LABELS['t2_label'],
                't3_label': NEAR_SURFACE_LABELS['t3_label'],
                'install_start': first_seen[sensor_id].strftime('%Y-%m-%d %H:%M:%S'),
                'install_end': None,
                'notes': 'Auto-seeded from loaded data'
            }
            seed_data.append(row)

        # Save
        with open(metadata_file, 'w') as f:
            json.dump(seed_data, f, indent=2)

        return {
            "success": True,
            "seeded": True,
            "rows": len(seed_data),
            "message": f"Seeded {len(seed_data)} sensor(s) with default metadata"
        }
    except Exception as e:
        logger.error(f"Failed to seed metadata: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to seed metadata: {e}")


@router.get("/{session_id}/metadata/{table_name}")
async def get_metadata_table(
    session_id: str,
    table_name: str,
    pipeline_type: str = "tms"
):
    """Get metadata table for a session."""
    if table_name not in METADATA_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"Invalid table name: {table_name}")

    metadata_file = _get_metadata_file(session_id, pipeline_type, table_name)

    if not metadata_file.exists():
        # Return empty table with schema
        return {
            "columns": METADATA_SCHEMAS[table_name]["columns"],
            "data": []
        }

    try:
        with open(metadata_file, 'r') as f:
            data = json.load(f)

        return {
            "columns": METADATA_SCHEMAS[table_name]["columns"],
            "data": data
        }
    except Exception as e:
        logger.error(f"Failed to load metadata {table_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load metadata: {e}")


@router.put("/{session_id}/metadata/{table_name}")
async def update_metadata_table(
    session_id: str,
    table_name: str,
    data: List[Dict[str, Any]],
    pipeline_type: str = "tms"
):
    """Update metadata table for a session."""
    if table_name not in METADATA_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"Invalid table name: {table_name}")

    session_dir = store.session_dir(session_id, pipeline_type)
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    metadata_file = _get_metadata_file(session_id, pipeline_type, table_name)

    try:
        # Validate data has required columns
        if data:
            df = pd.DataFrame(data)
            expected_cols = METADATA_SCHEMAS[table_name]["columns"]
            # Reindex to ensure all columns exist
            df = df.reindex(columns=expected_cols)
            # Normalize back to dict
            data = _normalize_dataframe(df, table_name)

        # Save to file
        with open(metadata_file, 'w') as f:
            json.dump(data, f, indent=2)

        return {"success": True, "rows": len(data)}
    except Exception as e:
        logger.error(f"Failed to save metadata {table_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save metadata: {e}")


@router.post("/{session_id}/metadata/{table_name}/upload")
async def upload_metadata_file(
    session_id: str,
    table_name: str,
    file: UploadFile = File(...),
    skiprows: int = Form(0),
    pipeline_type: str = "tms"
):
    """Upload and parse a metadata file (CSV/JSON/XLSX)."""
    if table_name not in METADATA_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"Invalid table name: {table_name}")

    session_dir = store.session_dir(session_id, pipeline_type)
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    try:
        # Parse file
        df = _parse_uploaded_file(file, skiprows)

        # Return preview with columns for mapping (replace NaN with None for JSON serialization)
        preview_df = df.head(10).where(pd.notna(df.head(10)), None)
        return {
            "columns": list(df.columns),
            "preview": preview_df.to_dict(orient='records'),
            "total_rows": len(df)
        }
    except Exception as e:
        logger.error(f"Failed to parse uploaded file: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}")


@router.post("/{session_id}/metadata/{table_name}/import")
async def import_metadata_with_mapping(
    session_id: str,
    table_name: str,
    file: UploadFile = File(...),
    column_mapping: str = Form(...),  # JSON dict mapping file cols to schema cols
    skiprows: int = Form(0),
    pipeline_type: str = "tms"
):
    """Import metadata file with column mapping."""
    if table_name not in METADATA_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"Invalid table name: {table_name}")

    session_dir = store.session_dir(session_id, pipeline_type)
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    try:
        # Parse mapping
        mapping = json.loads(column_mapping)

        # Parse file
        df = _parse_uploaded_file(file, skiprows)

        # Apply column mapping
        mapped_df = pd.DataFrame()
        for target_col, source_col in mapping.items():
            if source_col and source_col in df.columns:
                mapped_df[target_col] = df[source_col]

        # Ensure all schema columns exist
        expected_cols = METADATA_SCHEMAS[table_name]["columns"]
        mapped_df = mapped_df.reindex(columns=expected_cols)

        # Get loaded sensors from merged stage to filter
        merged_file = session_dir / "merged.parquet"
        matched_df = mapped_df
        skipped = 0

        if merged_file.exists() and 'sensor_id' in mapped_df.columns:
            # Load sensor IDs from merged data
            merged_df_full = pd.read_parquet(merged_file)
            loaded_sensors = set(merged_df_full['sensor_id'].astype(str).unique())

            # Filter to only sensors that have been loaded
            matched_df = mapped_df[mapped_df['sensor_id'].astype(str).isin(loaded_sensors)]
            skipped = len(mapped_df) - len(matched_df)

        # Load existing data and merge by sensor
        metadata_file = _get_metadata_file(session_id, pipeline_type, table_name)
        existing_data = []
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                existing_data = json.load(f)

        existing_df = pd.DataFrame(existing_data) if existing_data else pd.DataFrame(columns=expected_cols)

        # Merge by sensor: update existing sensors or append new ones
        added = 0
        updated = 0

        if not existing_df.empty and 'sensor_id' in existing_df.columns:
            sensor_counts = existing_df['sensor_id'].value_counts()

            for idx, row in matched_df.iterrows():
                sensor_id = str(row['sensor_id'])
                if sensor_counts.get(sensor_id) == 1:
                    # Update existing row
                    existing_idx = existing_df.index[existing_df['sensor_id'] == sensor_id][0]
                    for col, val in row.items():
                        if col != 'sensor_id' and pd.notna(val):
                            existing_df.at[existing_idx, col] = val
                    updated += 1
                else:
                    # Append new row
                    existing_df = pd.concat([existing_df, row.to_frame().T], ignore_index=True)
                    added += 1
        else:
            # No existing data, append all
            existing_df = pd.concat([existing_df, matched_df], ignore_index=True)
            added = len(matched_df)

        # Save
        merged_data = _normalize_dataframe(existing_df, table_name)
        with open(metadata_file, 'w') as f:
            json.dump(merged_data, f, indent=2)

        return {
            "success": True,
            "rows_added": added,
            "rows_updated": updated,
            "rows_skipped": skipped,
            "total_rows": len(existing_df)
        }
    except Exception as e:
        logger.error(f"Failed to import metadata: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to import: {e}")
