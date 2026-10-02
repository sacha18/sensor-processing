"""Step 6: final QC - inspect corrected Signal, VWC and temperature channels
together (cross-channel), on top of the per-channel initial QC from step 3.

The raw record is never touched here (t1_raw/t2_raw/t3_raw/signal_raw stay
exactly as parsed) - only the derived _final columns get NaN'd where a
cross-channel check fails, so a flagged reading is inspectable rather than
silently deleted.
"""
from __future__ import annotations

import pandas as pd

from ..common.qc_flags import flatline_flags
from .config import DEFAULT_FINAL_QC_CFG
from .events import field_event_flags


def detect_final_qc(calibrated: pd.DataFrame, final_qc_cfg: dict = None, field_events: pd.DataFrame = None) -> pd.DataFrame:
    cfg = {**DEFAULT_FINAL_QC_CFG, **(final_qc_cfg or {})}
    out = calibrated.copy()

    out["is_final_qc_vwc_range"] = out["vwc"].notna() & ((out["vwc"] < cfg["vwc_min"]) | (out["vwc"] > cfg["vwc_max"]))
    out["is_final_qc_freezing"] = out["t1_qc"].notna() & (out["t1_qc"] < cfg["freeze_threshold_c"])

    if cfg["use_flatline"]:
        out["is_final_qc_vwc_flatline"] = out.groupby("sensor_id")["vwc"].transform(
            lambda s: flatline_flags(s, cfg["flatline_min_run"])
        )
    else:
        out["is_final_qc_vwc_flatline"] = False

    # a field event logged against "vwc"/"all" (e.g. a whole treatment during a
    # harvest/disturbance window) directly excludes the derived series, on top of
    # whatever it already excluded upstream in initial QC's raw channels
    out["is_final_qc_field_event"] = field_event_flags(out, "vwc", field_events)

    out["is_final_qc_cross_channel"] = False  # placeholder - no T1/T2/T3-vs-position plausibility rule supplied yet

    method_cols = ["is_final_qc_vwc_range", "is_final_qc_freezing", "is_final_qc_vwc_flatline",
                   "is_final_qc_field_event", "is_final_qc_cross_channel"]
    out["is_final_qc"] = out[method_cols].any(axis=1)

    out["signal_corrected_final"] = out["signal_corrected"].where(~out["is_final_qc"])
    out["vwc_final"] = out["vwc"].where(~out["is_final_qc"])
    return out
