"""TMS workflow's own top nav - same tab-bar look as ui/generic/nav.py's
render_nav, just parametrized with the TMS step names/icons and a separate
session key so switching pipeline modes doesn't strand the user on an
out-of-range tab."""
from __future__ import annotations

from ui.generic.nav import render_nav

TMS_STEP_NAMES = [
    "Loading & continuity", "Metadata", "Initial QC", "Signal correction",
    "VWC calibration", "Final QC", "Analysis", "Production dataset",
]
TMS_STEP_ICONS = [
    ":material/upload_file:", ":material/map:", ":material/warning:",
    ":material/tune:", ":material/water_drop:", ":material/fact_check:",
    ":material/insights:", ":material/dataset:",
]


def render_nav_tms() -> int:
    return render_nav(TMS_STEP_NAMES, TMS_STEP_ICONS, session_key="tms_step_idx")
