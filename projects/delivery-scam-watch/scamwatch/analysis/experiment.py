"""Synthetic vs real: how different is synthetic data, and does it help the model?

1. Pattern shares: tag real scam domains with generator A's pattern names and compare shares
   (pre-registered predictions 1-3).
2. Real-vs-synthetic test: a classifier tries to tell synthetic scam domains from real ones;
   AUC near 0.5 means realistic, near 1.0 means easy to spot (prediction 5).
3. Learning curves on a held-out REAL test set (grouped by registered domain):
   real only with 25-all labels, synthetic only (A, B), and real + synthetic (prediction 4).
"""

from __future__ import annotations

import csv
import re
from collections import Counter

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit, cross_val_predict

from ..config import PROJECT_ROOT
from ..synthetic import generator_b
from .features import brand_token, features, frame
from .model import MODEL_FEATURES, make_model, recall_at_precision

LOOKALIKE = re.compile(r"(fed3x|fede x|up5|u5ps|usp5|dh1|xn--)")


def tag_pattern(fqdn: str) -> str:
    f = features(fqdn)
    reg = fqdn.split(".")[-2] if fqdn.count(".") >= 1 else fqdn
    if f["hosting_platform"]:
        return "hosting_platform (not in A)"
    if LOOKALIKE.search(fqdn) or f["punycode"]:
        return "lookalike_chars"
    if f["brand_only_in_subdomain"]:
        if f["entropy_longest_label"] > 3.0 and f["service_words"] == 0:
            return "random_with_brand_subdomain"
        return "brand_subdomain"
    if f["near_brand_spelling"] and not re.search(r"fedex|usps|dhl|ups", fqdn):
        return "misspelled_brand"
    if any(ch.isdigit() for ch in reg):
        return "brand_numbers"
    m = re.search(r"fedex|usps|dhl|ups", reg)
    svc = re.search(r"track|deliver|parcel|package|ship|post|customs|fee|pay|help|support|care|notice|update", reg)
    if m and svc:
        return "brand_service" if m.start() < svc.start() else "service_brand"
    return "other (brand only, or not in A)"


def load_generator_a() -> pd.DataFrame:
    rows = list(csv.DictReader((PROJECT_ROOT / "data" / "synthetic" / "generator_a_domains.csv").open()))
    df = pd.DataFrame(rows)
    df["brand"] = df.domain.apply(brand_token)
    return df


def pattern_shares(real_scams: list[str], a: pd.DataFrame) -> pd.DataFrame:
    real = Counter(tag_pattern(d) for d in real_scams)
    syn = Counter(a[a.label == "scam"].pattern)
    names = sorted(set(real) | set(syn))
    return pd.DataFrame(
        {
            "real_share": [real[n] / sum(real.values()) for n in names],
            "generator_a_share": [syn[n] / sum(syn.values()) for n in names],
        },
        index=names,
    ).round(3)


def tld_comparison(real_scams: pd.DataFrame, a: pd.DataFrame) -> dict:
    from ..store import split_domain

    real_tlds = Counter(real_scams.tld)
    a_tlds = Counter(split_domain(d).tld for d in a[a.label == "scam"].domain)
    top_real = [t for t, _ in real_tlds.most_common(10)]
    return {
        "real_top_endings": {t: round(real_tlds[t] / len(real_scams), 3) for t in top_real},
        "share_of_real_scams_with_endings_A_never_uses": round(
            sum(c for t, c in real_tlds.items() if t not in a_tlds) / len(real_scams), 3
        ),
    }


def distinguishability(real: list[str], synthetic: list[str], seed: int = 7) -> float:
    """AUC of a classifier separating real from synthetic scam domains (cross-validated)."""
    X = frame(real + synthetic)[MODEL_FEATURES]
    y = np.array([0] * len(real) + [1] * len(synthetic))
    s = cross_val_predict(make_model("gbm"), X, y, cv=5, method="predict_proba")[:, 1]
    return round(float(roc_auc_score(y, s)), 3)


def _fit_score(train_domains: list[str], train_y: np.ndarray, test_X: pd.DataFrame, test_y: np.ndarray) -> dict:
    if len(set(train_y)) < 2:
        return {"pr_auc": None, "recall_at_95_precision": None}
    m = make_model("gbm").fit(frame(train_domains)[MODEL_FEATURES], train_y)
    s = m.predict_proba(test_X)[:, 1]
    r, _ = recall_at_precision(test_y, s, 0.95)
    return {"pr_auc": round(float(average_precision_score(test_y, s)), 3), "recall_at_95_precision": round(r, 3)}


def learning_curves(
    labelled: pd.DataFrame, a: pd.DataFrame, sizes=(25, 50, 100, 200, 400, None), repeats: int = 5, seed: int = 7
) -> dict:
    split = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=seed)
    tr_idx, te_idx = next(split.split(labelled, groups=labelled.registered_domain))
    train, test = labelled.iloc[tr_idx], labelled.iloc[te_idx]
    test_X = frame(test.fqdn.tolist())[MODEL_FEATURES]
    test_y = (test.label == "scam").astype(int).values

    a_in_scope = a[a.brand.notna()]
    a_domains, a_y = a_in_scope.domain.tolist(), (a_in_scope.label == "scam").astype(int).values
    b_rows = generator_b.generate(list(zip(train.fqdn, train.tld, train.label, strict=True)), n=5000)
    b_domains, b_y = [d for d, _ in b_rows], np.array([int(lab == "scam") for _, lab in b_rows])

    res = {
        "test_size": len(test),
        "test_scams": int(test_y.sum()),
        "synthetic_only": {
            "generator_A": _fit_score(a_domains, a_y, test_X, test_y),
            "generator_B": _fit_score(b_domains, b_y, test_X, test_y),
        },
        "curve": [],
    }
    rng = np.random.default_rng(seed)
    for n in sizes:
        row = {"real_labels": n or len(train)}
        picks = [
            train if n is None else train.iloc[rng.choice(len(train), n, replace=False)]
            for _ in range(repeats if n else 1)
        ]
        for name in ("real_only", "real+A", "real+B"):
            scores = []
            for i, pick in enumerate(picks):
                if name == "real+A":
                    extra_d, extra_y = a_domains, a_y
                elif name == "real+B":  # B may only learn from the SAME few real labels the model gets
                    rows = generator_b.generate(
                        list(zip(pick.fqdn, pick.tld, pick.label, strict=True)), n=2000, seed=seed + i
                    )
                    extra_d, extra_y = [d for d, _ in rows], np.array([int(lab == "scam") for _, lab in rows])
                else:
                    extra_d, extra_y = [], np.array([], int)
                d = pick.fqdn.tolist() + extra_d
                y = np.concatenate([(pick.label == "scam").astype(int).values, extra_y])
                scores.append(_fit_score(d, y, test_X, test_y))
            ok = [s for s in scores if s["pr_auc"] is not None]
            row[name] = {
                k: round(float(np.mean([s[k] for s in ok])), 3) if ok else None
                for k in ("pr_auc", "recall_at_95_precision")
            }
        res["curve"].append(row)
    res["generator_B_examples"] = b_domains[:8]
    res["real_vs_B_auc"] = distinguishability(
        train[train.label == "scam"].fqdn.tolist()[:1500], [d for d, y in zip(b_domains, b_y, strict=True) if y][:1500]
    )
    return res
