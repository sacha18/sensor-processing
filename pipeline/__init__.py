"""Pipeline package: one subpackage per data pipeline.

- pipeline.generic - the generic single-value sensor pipeline
- pipeline.tms - the TOMST TMS-4 soil-sensor pipeline

Each subpackage is self-contained and re-exports its own public API
(`import pipeline.generic as P`, `import pipeline.tms as TMS`).
"""
from __future__ import annotations
