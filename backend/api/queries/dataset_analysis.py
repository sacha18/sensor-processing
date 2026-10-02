"""DuckDB queries for dataset statistical analysis.

These queries compute aggregated statistics, distributions, and group comparisons
for published datasets. They are designed to work with Parquet files containing
sensor data with optional grouping columns (treatment, site, depth_cm, position).

Nominal use cases:
- Daily/monthly trend analysis for time series visualization
- Distribution analysis for box plots and histograms
- Summary statistics for data quality checks and reporting
"""


def build_daily_stats_query(
    parquet_path: str,
    value_col: str,
    has_sensor_id: bool,
    group_cols: list[str],
    limit: int = 10000
) -> str:
    """Build query for daily statistics per sensor and group.

    Nominal use case:
        Generate daily aggregated values for time series charts showing individual
        sensor trends and group averages. Used for QA/QC visualization and
        detecting sensor drift or anomalies over time.

    Args:
        parquet_path: Path to the Parquet file
        value_col: Name of the value column to aggregate (e.g., 'vwc_final')
        has_sensor_id: Whether the dataset has a sensor_id column
        group_cols: List of grouping columns (e.g., ['treatment', 'site'])
        limit: Maximum number of rows to return

    Returns:
        SQL query string
    """
    group_cols_select = (', ' + ', '.join(group_cols)) if group_cols else ''

    query = f"""
        SELECT
            DATE_TRUNC('day', timestamp) as date,
            {'sensor_id,' if has_sensor_id else ''}
            {', '.join(group_cols) + ',' if group_cols else ''}
            AVG({value_col}) as mean,
            MAX({value_col}) as max,
            MIN({value_col}) as min,
            STDDEV({value_col}) as std,
            COUNT({value_col}) as n
        FROM '{parquet_path}'
        WHERE {value_col} IS NOT NULL
        GROUP BY date{', sensor_id' if has_sensor_id else ''}{group_cols_select}
        ORDER BY date
        LIMIT {limit}
    """
    return query


def build_daily_group_means_query(
    parquet_path: str,
    value_col: str,
    group_cols: list[str]
) -> str:
    """Build query for daily group means (average across sensors per day).

    Nominal use case:
        Compute treatment/group-level daily averages by first aggregating per sensor,
        then averaging across sensors. This prevents over-weighting sensors with more
        observations. Used for plotting thick "group average" lines over individual
        sensor traces.

    Args:
        parquet_path: Path to the Parquet file
        value_col: Name of the value column to aggregate
        group_cols: List of grouping columns

    Returns:
        SQL query string
    """
    group_cols_select = (', ' + ', '.join(group_cols)) if group_cols else ''

    query = f"""
        WITH daily_per_sensor AS (
            SELECT
                DATE_TRUNC('day', timestamp) as date,
                sensor_id,
                {', '.join(group_cols)},
                AVG({value_col}) as mean
            FROM '{parquet_path}'
            WHERE {value_col} IS NOT NULL
            GROUP BY date, sensor_id{group_cols_select}
        )
        SELECT
            date,
            {', '.join(group_cols)},
            AVG(mean) as group_mean,
            COUNT(DISTINCT sensor_id) as n_sensors
        FROM daily_per_sensor
        GROUP BY date{group_cols_select}
        ORDER BY date
    """
    return query


def build_monthly_stats_query(
    parquet_path: str,
    value_col: str,
    has_sensor_id: bool,
    group_cols: list[str],
    limit: int = 10000
) -> str:
    """Build query for monthly statistics per sensor and group.

    Nominal use case:
        Generate monthly aggregated values for seasonal analysis and year-over-year
        comparisons. Used for bar charts and seasonal trend visualization.

    Args:
        parquet_path: Path to the Parquet file
        value_col: Name of the value column to aggregate
        has_sensor_id: Whether the dataset has a sensor_id column
        group_cols: List of grouping columns
        limit: Maximum number of rows to return

    Returns:
        SQL query string
    """
    group_cols_select = (', ' + ', '.join(group_cols)) if group_cols else ''

    query = f"""
        SELECT
            STRFTIME(timestamp, '%Y-%m') as month,
            {'sensor_id,' if has_sensor_id else ''}
            {', '.join(group_cols) + ',' if group_cols else ''}
            AVG({value_col}) as mean,
            MAX({value_col}) as max,
            MIN({value_col}) as min,
            STDDEV({value_col}) as std,
            COUNT({value_col}) as n
        FROM '{parquet_path}'
        WHERE {value_col} IS NOT NULL
        GROUP BY month{', sensor_id' if has_sensor_id else ''}{group_cols_select}
        ORDER BY month
        LIMIT {limit}
    """
    return query


def build_distribution_query(
    parquet_path: str,
    value_col: str,
    has_sensor_id: bool,
    group_cols: list[str],
    limit: int = 10000
) -> str:
    """Build query for full value distribution by month.

    Nominal use case:
        Retrieve raw value distributions for box plot visualization. Shows outliers,
        quartiles, and median values to identify data quality issues, seasonal
        patterns, and sensor behavior differences.

    Args:
        parquet_path: Path to the Parquet file
        value_col: Name of the value column
        has_sensor_id: Whether the dataset has a sensor_id column
        group_cols: List of grouping columns
        limit: Maximum number of rows to return

    Returns:
        SQL query string
    """
    query = f"""
        SELECT
            {'sensor_id,' if has_sensor_id else ''}
            {', '.join(group_cols) + ',' if group_cols else ''}
            STRFTIME(timestamp, '%Y-%m') as month,
            {value_col} as value
        FROM '{parquet_path}'
        WHERE {value_col} IS NOT NULL
        ORDER BY month
        LIMIT {limit}
    """
    return query


def build_summary_stats_query(
    parquet_path: str,
    value_col: str,
    has_sensor_id: bool,
    group_cols: list[str],
    limit: int = 10000
) -> str:
    """Build query for overall summary statistics by sensor/group.

    Nominal use case:
        Generate comprehensive statistical summaries (count, mean, std, quartiles,
        min/max) for each sensor and group. Used for data quality reports, comparing
        sensor performance, and identifying outlier sensors or treatments.

    Args:
        parquet_path: Path to the Parquet file
        value_col: Name of the value column
        has_sensor_id: Whether the dataset has a sensor_id column
        group_cols: List of grouping columns
        limit: Maximum number of rows to return

    Returns:
        SQL query string
    """
    group_cols_select = (', ' + ', '.join(group_cols)) if group_cols else ''

    query = f"""
        SELECT
            {'sensor_id,' if has_sensor_id else ''}
            {', '.join(group_cols) + ',' if group_cols else ''}
            COUNT({value_col}) as count,
            AVG({value_col}) as mean,
            STDDEV({value_col}) as std,
            MIN({value_col}) as min,
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {value_col}) as q25,
            PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY {value_col}) as median,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {value_col}) as q75,
            MAX({value_col}) as max
        FROM '{parquet_path}'
        WHERE {value_col} IS NOT NULL
        GROUP BY {'sensor_id' if has_sensor_id else '1'}{group_cols_select}
        LIMIT {limit}
    """
    return query
