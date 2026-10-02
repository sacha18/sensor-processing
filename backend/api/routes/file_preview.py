"""Endpoints for previewing/parsing uploaded files without creating a session."""
from fastapi import APIRouter, File, UploadFile, HTTPException, Form
import pandas as pd
import json
import io
from pathlib import Path
from typing import Dict, Any

router = APIRouter(prefix="/api/preview", tags=["file-preview"])


@router.post("/parse-file")
async def parse_file_preview(
    file: UploadFile = File(...),
    skiprows: int = Form(0)
) -> Dict[str, Any]:
    """Parse uploaded file and return column names and preview data.

    Used for column mapping UI before actual file import.
    """
    try:
        content = await file.read()
        suffix = Path(file.filename).suffix.lower()

        # Parse based on file type
        if suffix == ".json":
            data = json.loads(content.decode("utf-8"))
            df = pd.DataFrame(data)
        elif suffix == ".xlsx":
            df = pd.read_excel(io.BytesIO(content), skiprows=skiprows)
        elif suffix in [".csv", ".txt"]:
            df = pd.read_csv(io.BytesIO(content), skiprows=skiprows)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format: {suffix}. Accepted: .json, .csv, .xlsx"
            )

        # Limit preview rows
        preview_df = df.head(10)

        # Convert to JSON-friendly format
        import numpy as np
        preview_df = preview_df.replace({np.nan: None})

        # Convert timestamps to strings
        for col in preview_df.select_dtypes(include=['datetime64']).columns:
            preview_df[col] = preview_df[col].astype(str)

        return {
            "columns": list(df.columns),
            "total_rows": len(df),
            "preview": preview_df.to_dict('records'),
        }

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse file: {str(e)}"
        )
