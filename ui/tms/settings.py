"""TMS pipeline settings: per-channel initial-QC and cross-channel final-QC
parameters, session_state-backed the same way as ui/generic/settings.py -
widgets live in ui/tms/sidebar.py, scoped to whichever TMS step is active, and
write straight back into this store so a value picked on one step is still in
effect after navigating away and back.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

import streamlit as st

from pipeline.tms.config import DEFAULT_FINAL_QC_CFG, DEFAULT_TMS_QC_CFG


@dataclass
class TmsSettings:
    qc_cfg: dict
    final_qc_cfg: dict
    step_min: int | None


def _fresh() -> dict:
    return {
        "qc_cfg": copy.deepcopy(DEFAULT_TMS_QC_CFG),
        "final_qc_cfg": dict(DEFAULT_FINAL_QC_CFG),
        "step_min": None,  # None -> inferred per sensor from its modal timestamp gap
    }


def init_tms_settings() -> None:
    st.session_state.setdefault("tms_settings", _fresh())


def store() -> dict:
    return st.session_state.tms_settings


def get_tms_settings() -> TmsSettings:
    s = store()
    return TmsSettings(qc_cfg=s["qc_cfg"], final_qc_cfg=s["final_qc_cfg"], step_min=s["step_min"])
