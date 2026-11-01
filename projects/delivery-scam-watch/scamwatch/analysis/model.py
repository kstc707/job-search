"""Stage 2 detector and its evaluation.

Stage 1 (a rule): keep only names that mention a delivery brand as a word of its own.
Stage 2 (this model): among those, which are scams?

Evaluation is deliberately strict:
  - grouped by registered domain, so subdomains of one site never sit in both train and test;
  - leave-one-brand-out: train on three brands, test on the fourth, to see whether it catches
    scams for a brand it never saw (a new campaign target);
because scam kits stamp out near-identical names, a plain random split would overstate accuracy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .features import FEATURES

MODEL_FEATURES = [f for f in FEATURES if f != "brand_token"]  # brand_token defines the scope; never an input


def make_model(kind: str = "gbm"):
    if kind == "logistic":
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))
    return HistGradientBoostingClassifier(
        max_iter=200, learning_rate=0.05, max_leaf_nodes=15, class_weight="balanced", random_state=7
    )


def recall_at_precision(y, scores, target: float) -> tuple[float, float]:
    """Highest recall reachable while keeping precision >= target, and the score threshold for it."""
    p, r, t = precision_recall_curve(y, scores)
    ok = np.where(p[:-1] >= target)[0]
    if not len(ok):
        return 0.0, float("inf")
    best = ok[np.argmax(r[:-1][ok])]
    return float(r[best]), float(t[best])


def out_of_fold(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, kind: str = "gbm", folds: int = 5) -> np.ndarray:
    scores = np.zeros(len(y))
    for train, test in GroupKFold(n_splits=folds).split(X, y, groups):
        m = make_model(kind).fit(X.iloc[train], y[train])
        scores[test] = m.predict_proba(X.iloc[test])[:, 1]
    return scores


def evaluate(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, brands: np.ndarray) -> dict:
    out = {"n_scam": int(y.sum()), "n_legitimate": int((1 - y).sum()), "grouped_cv": {}, "leave_one_brand_out": {}}
    for kind in ("logistic", "gbm"):
        s = out_of_fold(X, y, groups, kind)
        r95, _ = recall_at_precision(y, s, 0.95)
        out["grouped_cv"][kind] = {
            "pr_auc": round(float(average_precision_score(y, s)), 3),
            "recall_at_95_precision": round(r95, 3),
        }
    for held in sorted(set(brands)):
        tr, te = brands != held, brands == held
        if y[te].min() == y[te].max():  # needs both classes to score
            continue
        m = make_model("gbm").fit(X[tr], y[tr])
        s = m.predict_proba(X[te])[:, 1]
        out["leave_one_brand_out"][held] = {
            "n": int(te.sum()),
            "pr_auc": round(float(average_precision_score(y[te], s)), 3),
        }
    return out
