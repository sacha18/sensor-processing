"""Validators for TMS pipeline configuration files."""
import json
import pandas as pd
import io
from pathlib import Path
from typing import Dict, Any, List
from fastapi import UploadFile


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


async def _read_file_content(file: UploadFile) -> bytes:
    """Read file content, works with both sync and async file objects."""
    # Reset file pointer
    await file.seek(0)
    return await file.read()


def _normalize_column_name(col: str) -> str:
    """Normalize column name: lowercase, strip whitespace, replace spaces with underscores."""
    return col.strip().lower().replace(' ', '_')


def _normalize_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize DataFrame column names to standard format."""
    # Create a copy to avoid modifying the original
    df = df.copy()

    # Normalize all column names
    df.columns = [_normalize_column_name(col) for col in df.columns]

    return df


def _parse_file_to_dataframe(content: bytes, filename: str, skiprows: int = 0) -> pd.DataFrame:
    """Parse file content to DataFrame based on file extension."""
    suffix = Path(filename).suffix.lower()

    try:
        if suffix == ".json":
            data = json.loads(content.decode("utf-8"))
            df = pd.DataFrame(data)
        elif suffix == ".xlsx":
            df = pd.read_excel(io.BytesIO(content), skiprows=skiprows)
        elif suffix in [".csv", ".txt"]:
            df = pd.read_csv(io.BytesIO(content), skiprows=skiprows)
        else:
            raise ValidationError(f"Unsupported file format: {suffix}. Accepted: .json, .csv, .xlsx")

        # Normalize column names (case-insensitive, trim whitespace)
        df = _normalize_dataframe_columns(df)

        return df
    except Exception as e:
        raise ValidationError(f"Failed to parse file: {str(e)}")


async def validate_metadata_file(file: UploadFile) -> Dict[str, Any]:
    """
    Validate metadata configuration file.

    Required columns:
    - sensor_id

    Optional columns:
    - group_key, site, treatment, position, position_depth, row, transect, depth_cm
    - t1_label, t2_label, t3_label
    - install_start, install_end, notes

    Returns:
        Dict with validation result and parsed data
    """
    content = await _read_file_content(file)
    df = _parse_file_to_dataframe(content, file.filename)

    # Check for required column
    if 'sensor_id' not in df.columns:
        raise ValidationError("Missing required column: 'sensor_id'")

    # Check for empty data
    if df.empty:
        raise ValidationError("File contains no data rows")

    # Validate sensor_id is not null
    if df['sensor_id'].isna().any():
        raise ValidationError("sensor_id column contains null values")

    # Valid columns (defined in metadata.py METADATA_SCHEMAS)
    valid_columns = [
        "sensor_id", "group_key", "site", "treatment", "position", "position_depth",
        "row", "transect", "depth_cm", "t1_label", "t2_label", "t3_label",
        "install_start", "install_end", "notes"
    ]

    # Warn about extra columns (but don't fail)
    extra_cols = set(df.columns) - set(valid_columns)
    warnings = []
    if extra_cols:
        warnings.append(f"Extra columns will be ignored: {', '.join(extra_cols)}")

    return {
        "valid": True,
        "rows": len(df),
        "columns": list(df.columns),
        "sensors": df['sensor_id'].nunique(),
        "warnings": warnings
    }


async def validate_qc_params_file(file: UploadFile) -> Dict[str, Any]:
    """
    Validate QC parameters JSON file.

    Expected structure:
    {
      "qc_cfg": {
        "t1": { "use_hampel": true, "hampel_k": 3.0, ... },
        "t2": { ... },
        "t3": { ... },
        "signal": { ... }
      },
      "correction_table": [...],  // optional
      "calibration_table": [...],  // optional
      "field_events": [...]  // optional
    }

    Returns:
        Dict with validation result
    """
    content = await _read_file_content(file)

    try:
        data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid JSON format: {str(e)}")

    # Check for qc_cfg key
    if "qc_cfg" not in data:
        raise ValidationError("Missing required key: 'qc_cfg'")

    qc_cfg = data["qc_cfg"]
    if not isinstance(qc_cfg, dict):
        raise ValidationError("'qc_cfg' must be a dictionary")

    # Required channels
    required_channels = ["t1", "t2", "t3", "signal"]
    missing_channels = [ch for ch in required_channels if ch not in qc_cfg]
    if missing_channels:
        raise ValidationError(f"Missing QC config for channels: {', '.join(missing_channels)}")

    # Validate each channel has required fields
    required_fields = [
        "use_hampel", "hampel_k", "hampel_half_window",
        "use_flatline", "flatline_min_run",
        "use_percentile", "pct_low", "pct_high",
        "use_rate", "rate_k"
    ]

    for channel, config in qc_cfg.items():
        if channel not in required_channels:
            continue  # Skip extra channels

        if not isinstance(config, dict):
            raise ValidationError(f"Channel '{channel}' config must be a dictionary")

        missing_fields = [f for f in required_fields if f not in config]
        if missing_fields:
            raise ValidationError(
                f"Channel '{channel}' missing fields: {', '.join(missing_fields)}"
            )

    warnings = []

    # Validate optional tables if present
    if "correction_table" in data and not isinstance(data["correction_table"], list):
        raise ValidationError("'correction_table' must be a list")

    if "calibration_table" in data and not isinstance(data["calibration_table"], list):
        raise ValidationError("'calibration_table' must be a list")

    if "field_events" in data and not isinstance(data["field_events"], list):
        raise ValidationError("'field_events' must be a list")

    return {
        "valid": True,
        "channels": list(qc_cfg.keys()),
        "has_corrections": "correction_table" in data and len(data.get("correction_table", [])) > 0,
        "has_calibrations": "calibration_table" in data and len(data.get("calibration_table", [])) > 0,
        "has_field_events": "field_events" in data and len(data.get("field_events", [])) > 0,
        "warnings": warnings
    }


async def validate_corrections_file(file: UploadFile) -> Dict[str, Any]:
    """
    Validate corrections configuration file.

    Required columns:
    - sensor_id
    - correction_type (one_factor or two_factor)
    - factor_a

    Optional columns:
    - factor_b (required for two_factor)
    - valid_from, valid_to, notes

    Returns:
        Dict with validation result
    """
    content = await _read_file_content(file)
    df = _parse_file_to_dataframe(content, file.filename)

    # Check for required columns
    required_cols = ['sensor_id', 'correction_type', 'factor_a']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValidationError(f"Missing required columns: {', '.join(missing_cols)}")

    # Check for empty data
    if df.empty:
        raise ValidationError("File contains no data rows")

    # Validate sensor_id is not null
    if df['sensor_id'].isna().any():
        raise ValidationError("sensor_id column contains null values")

    # Validate correction_type values
    valid_types = ['one_factor', 'two_factor', 'identity']
    invalid_types = df[~df['correction_type'].isin(valid_types)]['correction_type'].unique()
    if len(invalid_types) > 0:
        raise ValidationError(
            f"Invalid correction_type values: {', '.join(map(str, invalid_types))}. "
            f"Valid types: {', '.join(valid_types)}"
        )

    # Validate factor_a is not null
    if df['factor_a'].isna().any():
        raise ValidationError("factor_a column contains null values")

    # For two_factor corrections, factor_b must be present and not null
    two_factor_rows = df[df['correction_type'] == 'two_factor']
    if not two_factor_rows.empty:
        if 'factor_b' not in df.columns:
            raise ValidationError("factor_b column required for two_factor corrections")
        if two_factor_rows['factor_b'].isna().any():
            raise ValidationError("factor_b cannot be null for two_factor corrections")

    warnings = []

    # Count wildcard rules
    wildcard_count = (df['sensor_id'] == '*').sum()
    if wildcard_count > 1:
        warnings.append(f"Multiple wildcard (*) rules found ({wildcard_count}). Only the last one will apply.")

    return {
        "valid": True,
        "rows": len(df),
        "columns": list(df.columns),
        "sensors": df[df['sensor_id'] != '*']['sensor_id'].nunique(),
        "has_wildcard": wildcard_count > 0,
        "correction_types": df['correction_type'].value_counts().to_dict(),
        "warnings": warnings
    }


async def validate_calibrations_file(file: UploadFile) -> Dict[str, Any]:
    """
    Validate calibrations configuration file.

    Required columns:
    - sensor_id
    - At least one coef_* column (coef_0 to coef_5)

    Optional columns:
    - valid_from, valid_to, notes

    Returns:
        Dict with validation result
    """
    content = await _read_file_content(file)
    df = _parse_file_to_dataframe(content, file.filename)

    # Check for required column
    if 'sensor_id' not in df.columns:
        raise ValidationError("Missing required column: 'sensor_id'")

    # Check for empty data
    if df.empty:
        raise ValidationError("File contains no data rows")

    # Validate sensor_id is not null
    if df['sensor_id'].isna().any():
        raise ValidationError("sensor_id column contains null values")

    # Check for at least one coefficient column
    coef_cols = [f'coef_{i}' for i in range(6)]
    present_coefs = [col for col in coef_cols if col in df.columns]

    if not present_coefs:
        raise ValidationError(
            f"At least one coefficient column required: {', '.join(coef_cols)}"
        )

    # Validate that coef_0 is present (constant term)
    if 'coef_0' not in df.columns:
        raise ValidationError("coef_0 (constant term) is required")

    warnings = []

    # Count wildcard rules
    wildcard_count = (df['sensor_id'] == '*').sum()
    if wildcard_count > 1:
        warnings.append(f"Multiple wildcard (*) rules found ({wildcard_count}). Only the last one will apply.")

    # Determine polynomial degree
    max_degree = max([int(col.split('_')[1]) for col in present_coefs])

    return {
        "valid": True,
        "rows": len(df),
        "columns": list(df.columns),
        "sensors": df[df['sensor_id'] != '*']['sensor_id'].nunique(),
        "has_wildcard": wildcard_count > 0,
        "coefficients": present_coefs,
        "max_polynomial_degree": max_degree,
        "warnings": warnings
    }
