"""Similarity between sensors: correlation on levels (overall behaviour) and
on first differences (do sensors move together, event by event?) -> used to
pick a gap-fill donor.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform


def similarity(reg_long: pd.DataFrame) -> dict:
    wide_qc = reg_long.pivot(index="timestamp", columns="sensor_id", values="value_qc").sort_index()
    cor_level = wide_qc.corr()
    cor_diff = wide_qc.diff().corr()

    dist = 1 - cor_level.abs()
    dist_vals = np.array(dist.values, copy=True)
    np.fill_diagonal(dist_vals, 0.0)
    # linkage/squareform need >=2 observations - a single-sensor dataset has no
    # pairwise distances to cluster, so there's nothing to compute
    Z = linkage(squareform(dist_vals, checks=False), method="average") if len(dist_vals) >= 2 else None

    donor_of = {}
    for s in cor_level.columns:
        cc = cor_level[s].drop(index=s)
        donor_of[s] = cc.idxmax() if cc.notna().any() else None

    return {"wide_qc": wide_qc, "cor_level": cor_level, "cor_diff": cor_diff, "linkage": Z, "donor_of": donor_of, "labels": list(cor_level.columns)}
