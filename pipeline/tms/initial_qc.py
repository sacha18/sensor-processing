"""Step 3: initial QC - inspect T1/T2/T3 and raw Signal.

Each channel is QC'd independently (a bad Signal reading doesn't imply a bad
T2) by reusing the same toggleable flag methods as the generic pipeline's
outlier detection (pipeline/generic/outliers.py) - Hampel spike filter, flatline/
stuck-sensor run, extreme-value percentile bound, rate-of-change - applied
per channel instead of per sensor. Device-reported errors (err_flag != 0)
and any manually-logged field event covering that channel/time window are
folded in as additional flags. Poor-soil-contact detection (T1 only) has no
specified rule yet - the column exists (always False) so the schema is
stable once a real rule is supplied.
"""
from __future__ import annotations

import pandas as pd

from pipeline.generic.outliers import flatline_flags, hampel_flags, percentile_flags, rate_flags

from .config import DEFAULT_TMS_QC_CFG, ERR_FLAG_OK, SIGNAL_CHANNELS
from .events import field_event_flags


def detect_initial_qc(with_metadata: pd.DataFrame, qc_cfg: dict = None, field_events: pd.DataFrame = None) -> pd.DataFrame:
    cfg = qc_cfg or DEFAULT_TMS_QC_CFG
    out = with_metadata.copy()
    out["is_qc_device_error"] = out["err_flag"] != ERR_FLAG_OK

    for ch in SIGNAL_CHANNELS:
        col = f"{ch}_raw"
        c = {**DEFAULT_TMS_QC_CFG[ch], **(cfg.get(ch, {}))}
        g = out.groupby("sensor_id")[col]

        out[f"is_qc_hampel_{ch}"] = g.transform(lambda s: hampel_flags(s, c["hampel_half_window"], c["hampel_k"])) if c["use_hampel"] else False
        out[f"is_qc_flatline_{ch}"] = g.transform(lambda s: flatline_flags(s, c["flatline_min_run"])) if c["use_flatline"] else False
        out[f"is_qc_range_{ch}"] = g.transform(lambda s: percentile_flags(s, c["pct_low"], c["pct_high"])) if c["use_percentile"] else False
        out[f"is_qc_rate_{ch}"] = g.transform(lambda s: rate_flags(s, c["rate_k"])) if c["use_rate"] else False
        out[f"is_qc_field_event_{ch}"] = field_event_flags(out, ch, field_events)

        method_cols = [f"is_qc_hampel_{ch}", f"is_qc_flatline_{ch}", f"is_qc_range_{ch}", f"is_qc_rate_{ch}", f"is_qc_field_event_{ch}"]
        if ch == "t1":
            out["is_qc_poor_contact_t1"] = False  # placeholder - no domain rule supplied yet
            method_cols.append("is_qc_poor_contact_t1")

        out[f"is_qc_{ch}"] = out[method_cols].any(axis=1) | out["is_qc_device_error"]
        out[f"{ch}_qc"] = out[col].where(~out[f"is_qc_{ch}"])

    return out
