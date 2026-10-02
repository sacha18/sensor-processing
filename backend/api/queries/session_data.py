"""DuckDB queries for session stage data access.

These queries read intermediate pipeline stage results from session directories.
Each pipeline stage caches its output as Parquet files, which can be inspected
during interactive pipeline execution.

Nominal use cases:
- Fetching stage data for step-by-step pipeline visualization
- Debugging pipeline issues by inspecting intermediate results
- QC review of processing stages before final publication
"""

from typing import Optional


def build_stage_count_query(stage_file: str) -> str:
    """Build query to count rows in a pipeline stage file.

    Nominal use case:
        Quick row count for a pipeline stage to show data volume at each step,
        detect empty stages (pipeline failures), and calculate sampling ratios
        for large datasets.

    Args:
        stage_file: Path to the stage Parquet file

    Returns:
        SQL query string
    """
    return f"SELECT COUNT(*) as count FROM '{stage_file}'"


def build_stage_data_query(
    stage_file: str,
    columns: Optional[list[str]] = None,
    limit: int = 1000,
    offset: int = 0
) -> str:
    """Build query to fetch paginated data from a pipeline stage.

    Nominal use case:
        Retrieve stage data for frontend display, allowing users to inspect
        processing results at each pipeline step. Supports pagination for
        large datasets and column selection for performance.

    Args:
        stage_file: Path to the stage Parquet file
        columns: Optional list of columns to select (None = all columns)
        limit: Maximum number of rows to return
        offset: Number of rows to skip (for pagination)

    Returns:
        SQL query string
    """
    select_cols = ', '.join(columns) if columns else '*'

    query = f"""
        SELECT {select_cols}
        FROM '{stage_file}'
        LIMIT {limit}
        OFFSET {offset}
    """
    return query


def build_stage_sample_query(
    stage_file: str,
    columns: Optional[list[str]] = None,
    sample_size: int = 1000,
    total_rows: int = None
) -> str:
    """Build query to fetch evenly sampled data from a pipeline stage.

    Nominal use case:
        Sample stage data for performance when displaying large datasets.
        Samples every Nth row to maintain distribution while reducing
        data transfer. Used for preview/inspection of large stage results.

    Args:
        stage_file: Path to the stage Parquet file
        columns: Optional list of columns to select (None = all columns)
        sample_size: Number of rows to sample
        total_rows: Total number of rows (used to calculate step size)

    Returns:
        SQL query string
    """
    select_cols = ', '.join(columns) if columns else '*'
    step = max(1, total_rows // sample_size) if total_rows and sample_size > 0 else 1

    query = f"""
        WITH numbered AS (
            SELECT {select_cols}, ROW_NUMBER() OVER () as rn
            FROM '{stage_file}'
        )
        SELECT * EXCLUDE(rn)
        FROM numbered
        WHERE rn % {step} = 0
        LIMIT {sample_size}
    """
    return query


def build_empty_schema_query(
    stage_file: str,
    columns: Optional[list[str]] = None
) -> str:
    """Build query to get schema from empty stage file.

    Nominal use case:
        Get column names and types from a stage file with zero rows.
        Returns empty DataFrame with correct schema for display.

    Args:
        stage_file: Path to the stage Parquet file
        columns: Optional list of columns to select (None = all columns)

    Returns:
        SQL query string
    """
    select_cols = ', '.join(columns) if columns else '*'
    return f"SELECT {select_cols} FROM '{stage_file}' LIMIT 0"
