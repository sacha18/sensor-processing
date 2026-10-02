"""DuckDB queries for dataset preview and metadata inspection.

These queries are used to preview datasets, inspect schemas, and sample data
for visualization without loading entire Parquet files into memory.

Nominal use cases:
- Quick dataset previews for browsing published datasets
- Schema inspection for frontend column selection
- Sampled data for time series charts (performance optimization)
"""

from typing import Optional


def build_count_query(parquet_path: str) -> str:
    """Build query to count total rows in a Parquet file.

    Nominal use case:
        Quickly get the row count of a dataset for pagination, sampling calculations,
        and displaying dataset size in the UI. DuckDB's Parquet metadata reader makes
        this very fast (no full table scan).

    Args:
        parquet_path: Path to the Parquet file

    Returns:
        SQL query string
    """
    return f"SELECT COUNT(*) FROM '{parquet_path}'"


def build_schema_query(parquet_path: str) -> str:
    """Build query to get schema information (column names and types).

    Nominal use case:
        Inspect dataset schema to determine available columns, identify value columns,
        detect grouping columns (treatment, site, etc.), and validate expected structure
        before running analysis queries.

    Args:
        parquet_path: Path to the Parquet file

    Returns:
        SQL query string
    """
    return f"DESCRIBE SELECT * FROM '{parquet_path}' LIMIT 1"


def build_sample_query(
    parquet_path: str,
    sample_size: int,
    total_rows: int,
    columns: Optional[list[str]] = None
) -> str:
    """Build query to sample evenly distributed rows from a dataset.

    Nominal use case:
        Extract a representative sample of data for time series visualization.
        Samples every Nth row to maintain temporal distribution while reducing
        data transfer to the frontend. Much faster than random sampling for
        large datasets.

    Args:
        parquet_path: Path to the Parquet file
        sample_size: Number of rows to sample
        total_rows: Total number of rows in the dataset
        columns: Optional list of columns to select (None = all columns)

    Returns:
        SQL query string
    """
    step = max(1, total_rows // sample_size)
    select_cols = ', '.join(columns) if columns else '*'

    # Exclude the row number column from final output
    query = f"""
        WITH numbered AS (
            SELECT *, ROW_NUMBER() OVER () as rn
            FROM '{parquet_path}'
        )
        SELECT * EXCLUDE(rn)
        FROM numbered
        WHERE rn % {step} = 0
        LIMIT {sample_size}
    """
    return query
