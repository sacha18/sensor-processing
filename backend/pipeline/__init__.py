"""Pipeline package: the TMS pipeline, plus a shared toolbox.

- backend.pipeline.tms - the TOMST TMS-4 soil-sensor pipeline
- backend.pipeline.common - pipeline-agnostic building blocks (QC flag
  methods, DuckDB-backed dedup) used by it and reusable by any future
  pipeline; it has no stages/orchestration of its own

The TMS subpackage is self-contained and re-exports its own public API
(`import backend.pipeline.tms as TMS`).
"""
from __future__ import annotations
