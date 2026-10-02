"""DuckDB query builders for dataset analysis and operations.

This module provides reusable query builders for DuckDB operations,
making queries more maintainable and testable.
"""

from .dataset_analysis import (
    build_daily_stats_query,
    build_daily_group_means_query,
    build_monthly_stats_query,
    build_distribution_query,
    build_summary_stats_query,
)

from .dataset_preview import (
    build_count_query,
    build_schema_query,
    build_sample_query,
)

from .session_data import (
    build_stage_count_query,
    build_stage_data_query,
    build_stage_sample_query,
    build_empty_schema_query,
)

__all__ = [
    # Analysis queries
    "build_daily_stats_query",
    "build_daily_group_means_query",
    "build_monthly_stats_query",
    "build_distribution_query",
    "build_summary_stats_query",
    # Preview queries
    "build_count_query",
    "build_schema_query",
    "build_sample_query",
    # Session queries
    "build_stage_count_query",
    "build_stage_data_query",
    "build_stage_sample_query",
    "build_empty_schema_query",
]
