# DuckDB Query Builders

This directory contains all DuckDB query builders used by the backend API for data analysis and visualization.

## Organization

### `dataset_analysis.py`
**Queries for statistical analysis of published datasets**

Functions:
- `build_daily_stats_query()` - Daily statistics per sensor and group
- `build_daily_group_means_query()` - Daily group means (cross-sensor averages)
- `build_monthly_stats_query()` - Monthly statistics per sensor and group
- `build_distribution_query()` - Full value distribution for box plots
- `build_summary_stats_query()` - Summary statistics (count, mean, std, quartiles)

**Nominal use cases:**
- Temporal trend analysis (daily/monthly charts)
- Sensor anomaly detection and drift monitoring
- Treatment and group comparisons
- Visual QA/QC and statistical reporting

### `dataset_preview.py`
**Queries for dataset preview and inspection**

Functions:
- `build_count_query()` - Count rows in a Parquet file
- `build_schema_query()` - Inspect schema (columns and types)
- `build_sample_query()` - Sample uniformly for visualization

**Nominal use cases:**
- Quick dataset previews in the browse interface
- Automatic detection of value and grouping columns
- Performance optimization for charts (sampling)

### `session_data.py`
**Queries for accessing pipeline session data**

Functions:
- `build_stage_count_query()` - Count rows in a pipeline stage
- `build_stage_data_query()` - Retrieve paginated stage data
- `build_stage_sample_query()` - Sample stage data
- `build_empty_schema_query()` - Get schema from empty file

**Nominal use cases:**
- Step-by-step inspection of interactive pipeline
- Debugging pipeline issues
- QC review before publication

## Design Principles

### 1. Separation of Concerns
Each file groups queries by functional domain (analysis, preview, sessions).

### 2. Pure Functions
Query builders are pure functions that:
- Take typed parameters
- Return SQL strings
- Have no side effects
- Are easily testable

### 3. Explicit Documentation
Each function documents:
- **Nominal use case**: The primary intended usage
- **Args**: Parameters with their types
- **Returns**: Format of the returned query

### 4. Readability
SQL queries use:
- Clear indentation
- Comments in Python code (not in SQL)
- Explicit column and variable names

## Usage Example

```python
from backend.api.queries import build_daily_stats_query

# Build the query
query = build_daily_stats_query(
    parquet_path="/data/dataset.parquet",
    value_col="vwc_final",
    has_sensor_id=True,
    group_cols=["treatment", "site"],
    limit=10000
)

# Execute with DuckDB
import duckdb
con = duckdb.connect()
df = con.execute(query).df()
```

## Testing

All API endpoints using these query builders are tested:
- ✅ Preview endpoint (`/api/datasets/{id}/preview`)
- ✅ Analysis endpoints (`/api/datasets/{id}/analysis?analysis_type=...`)
- ✅ Session stage endpoints (`/api/sessions/{id}/stages/...`)

## Maintenance

When adding new queries:

1. **Create the function** in the appropriate file
2. **Document** with docstring including nominal use case
3. **Export** in `__init__.py`
4. **Import** in the route handler that uses it
5. **Test** the corresponding API endpoint
