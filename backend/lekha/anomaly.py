"""Anomaly detection on invoices and payments: robust z-score + IQR rules, plus IsolationForest.
Evaluated against the anomalies the generator injected (inflated invoices x4-9, mis-paid payments x0.4/x1.8)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


def _robust_z(log_amt: pd.Series, groups: pd.Series) -> pd.Series:
    med = log_amt.groupby(groups).transform("median")
    mad = (log_amt - med).abs().groupby(groups).transform("median")
    glob = (log_amt - log_amt.median()).abs().median()
    scale = (1.4826 * mad).where(mad > 0, 1.4826 * glob).clip(lower=0.15)
    return (log_amt - med) / scale


def detect_invoices(t: dict[str, pd.DataFrame], truth_keys: set[str], seed: int = 42, z_thr: float = 3.5, contamination: float = 0.02, match_tol: float = 0.05,
                    skip_orders: set | None = None) -> dict:
    v = t["VBRK"].copy()
    v["log_amt"] = np.log(v["NETWR"].clip(lower=1))
    v["rz"] = _robust_z(v["log_amt"], v["KUNNR"])
    cust_med = v.groupby("KUNNR")["NETWR"].transform("median")
    v["ratio"] = v["NETWR"] / cust_med
    # three-way match: invoice value vs delivered qty x order price
    dv = t["LIPS"].merge(t["LIKP"][["VBELN_VL", "VBELN"]], on="VBELN_VL").merge(t["VBAP"][["VBELN", "POSNR", "NETPR"]], on=["VBELN", "POSNR"])
    dv["val"] = dv["LFIMG"] * dv["NETPR"]
    v["expected"] = v["VBELN"].map(dv.groupby("VBELN")["val"].sum())
    v["match_ratio"] = (v["NETWR"] / v["expected"].replace(0, np.nan)).fillna(1.0)
    v["flag_match"] = ((v["match_ratio"] - 1).abs() > match_tol) & ~v["VBELN"].isin(skip_orders or set())
    q1, q3 = v["log_amt"].quantile([0.25, 0.75])
    iqr_hi = q3 + 1.5 * (q3 - q1)
    v["flag_z"] = v["rz"] > z_thr
    v["flag_iqr"] = v["log_amt"] > iqr_hi
    X = v[["log_amt", "rz", "ratio"]].to_numpy()
    iso = IsolationForest(n_estimators=200, contamination=contamination, random_state=seed).fit(X)
    v["iso_score"] = -iso.score_samples(X)
    v["flag_iso"] = iso.predict(X) == -1
    Xm = v[["log_amt", "rz", "ratio", "match_ratio"]].to_numpy()
    iso_m = IsolationForest(n_estimators=200, contamination=contamination, random_state=seed).fit(Xm)
    v["flag_iso_match"] = iso_m.predict(Xm) == -1
    v["flagged"] = v["flag_z"] | v["flag_iso"] | v["flag_match"]
    truth = v["VBELN_VF"].isin(truth_keys)
    ev = {}
    for name in ("flag_z", "flag_iqr", "flag_iso", "flag_iso_match", "flag_match", "flagged"):
        tp = int((v[name] & truth).sum())
        ev[name] = {"flagged": int(v[name].sum()), "true_positives": tp, "recall": tp / max(int(truth.sum()), 1),
                    "precision": tp / max(int(v[name].sum()), 1)}
    top = v[v["flagged"]].sort_values(["flag_match", "iso_score"], ascending=False)
    return {"injected_in_clean_data": int(truth.sum()), "rules": {"robust_z_threshold": z_thr, "iqr_log_upper_fence": float(iqr_hi),
            "isolation_forest_contamination": contamination, "three_way_match_tolerance": match_tol}, "evaluation": ev,
            "top": top.head(200).assign(injected=truth[top.head(200).index])[
                ["VBELN_VF", "KUNNR", "FKDAT", "NETWR", "ratio", "rz", "match_ratio", "iso_score", "flag_z", "flag_iqr", "flag_iso", "flag_match", "injected"]]}


def detect_payments(t: dict[str, pd.DataFrame], truth_keys: set[str], seed: int = 42, tol: float = 0.05) -> dict:
    p = t["BSAD"].merge(t["VBRK"][["VBELN_VF", "NETWR", "FKDAT", "KUNNR"]], on="VBELN_VF")
    p["ratio"] = p["DMBTR"] / p["NETWR"].replace(0, np.nan)
    p["dtp"] = (p["AUGDT"] - p["FKDAT"]).dt.days
    p["flag_rule"] = (p["ratio"] - 1).abs() > tol
    X = p[["ratio", "dtp"]].fillna(0).to_numpy()
    iso = IsolationForest(n_estimators=200, contamination=0.01, random_state=seed).fit(X)
    p["flag_iso"] = iso.predict(X) == -1
    truth = p["VBELN_VF"].isin(truth_keys)
    ev = {}
    for name in ("flag_rule", "flag_iso"):
        tp = int((p[name] & truth).sum())
        ev[name] = {"flagged": int(p[name].sum()), "true_positives": tp, "recall": tp / max(int(truth.sum()), 1),
                    "precision": tp / max(int(p[name].sum()), 1)}
    return {"injected_in_clean_data": int(truth.sum()), "evaluation": ev,
            "top": p[p["flag_rule"] | p["flag_iso"]].assign(injected=truth).head(100)[["VBELN_VF", "KUNNR", "AUGDT", "NETWR", "DMBTR", "ratio", "dtp", "flag_rule", "flag_iso", "injected"]]}
