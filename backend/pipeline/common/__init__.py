"""Pipeline-agnostic building blocks shared by every pipeline under
backend.pipeline (currently just .tms, but not specific to it) -
signal-processing flag methods, DuckDB-backed dedup, and similar primitives
that a new pipeline could reuse as-is rather than reimplementing.

Each pipeline still owns its own stage list and orchestration; this package
only holds the parts that don't depend on any pipeline-specific schema.
"""
from __future__ import annotations
