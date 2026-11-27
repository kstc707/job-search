"""Metrics. Kept separate from training so tests can check them on tiny hand-made inputs."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


def eta_metrics(y_true, y_pred) -> dict:
    err = np.abs(np.asarray(y_true, float) - np.asarray(y_pred, float))
    return {
        "mae_min": float(err.mean()),
        "median_ae_min": float(np.median(err)),
        "within_30_min": float((err <= 30).mean()),
    }


def flag_top_share(scores, budget: float) -> np.ndarray:
    """Flag the highest-scoring `budget` share of rows (ties broken by order, so exactly k flags)."""
    scores = np.asarray(scores, float)
    k = int(round(budget * len(scores)))
    flags = np.zeros(len(scores), dtype=bool)
    if k > 0:
        flags[np.argsort(-scores, kind="stable")[:k]] = True
    return flags


def alert_metrics(y_true, flags) -> dict:
    y = np.asarray(y_true).astype(bool)
    f = np.asarray(flags).astype(bool)
    tp = int((y & f).sum())
    return {
        "flagged_share": float(f.mean()),
        "recall": tp / max(int(y.sum()), 1),
        "precision": tp / max(int(f.sum()), 1),
        "true_alerts": tp,
        "late_total": int(y.sum()),
    }


def risk_metrics(y_true, scores, budget: float) -> dict:
    y = np.asarray(y_true).astype(int)
    out = {
        "roc_auc": float(roc_auc_score(y, scores)),
        "pr_auc": float(average_precision_score(y, scores)),
        "base_rate": float(y.mean()),
    }
    if np.all((np.asarray(scores) >= 0) & (np.asarray(scores) <= 1)):
        out["brier"] = float(brier_score_loss(y, scores))
    out.update({f"at_budget_{k}": v for k, v in alert_metrics(y, flag_top_share(scores, budget)).items()})
    return out


def calibration_table(y_true, scores, bins: int = 10) -> list[dict]:
    """Mean predicted vs observed late rate per score decile."""
    y = np.asarray(y_true, float)
    s = np.asarray(scores, float)
    order = np.argsort(s)
    rows = []
    for chunk in np.array_split(order, bins):
        rows.append({"mean_score": float(s[chunk].mean()), "late_rate": float(y[chunk].mean()), "n": int(len(chunk))})
    return rows
