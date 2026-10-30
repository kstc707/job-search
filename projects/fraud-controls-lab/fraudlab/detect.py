"""Three ways to build a review queue, scored the way a fraud team is judged: with a fixed
number of cases analysts can review each month, how much confirmed fraud (and how many
dollars) lands in the queue?

  rules        six transparent business controls; score = number of rules fired
  anomaly      Isolation Forest, unsupervised (no labels needed)
  supervised   gradient boosting trained on earlier months' confirmed cases
  expected_loss  the supervised probability times the dollars exposed (billed + claimed)
  hybrid       high-severity theft rules escalate first, expected loss ranks the rest (recommended)

Out-of-time split: train on months 1-7, test on months 8-11. Month 0 has no history, so it
is never scored.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest
from sklearn.metrics import average_precision_score

from .features import FEATURES
from .resample import Resampler, top_k_sum

TRAIN_MONTHS = range(1, 8)
TEST_MONTHS = range(8, 12)

RULES = {
    "R1_volume_spike": lambda f: (f.volume_ratio >= 4) & (f.n_ship >= 15),
    "R2_new_device_new_destinations": lambda f: (f.new_device_share >= 0.5) & (f.new_dest_share >= 0.5),
    "R3_under_declared_weight": lambda f: f.low_weight_share >= 0.3,
    "R4_shared_device": lambda f: f.max_device_accounts >= 3,
    "R5_claim_burst": lambda f: (f.n_claims >= 3) & (f.not_received_share >= 0.6),
    "R6_mule_address": lambda f: f.drop_dest_share >= 0.3,
}


def apply_rules(f: pd.DataFrame) -> pd.DataFrame:
    out = f.copy()
    for name, rule in RULES.items():
        out[name] = rule(out).astype(int)
    # rule count first, money at stake breaks ties (what an analyst would sort by)
    out["score_rules"] = out[list(RULES)].sum(axis=1) + out.billed.rank(pct=True) * 0.01
    return out


def fit_models(f: pd.DataFrame, seed: int = 7) -> pd.DataFrame:
    """Expects the rule columns from apply_rules()."""
    out = f.copy()
    train = out[out.month.isin(TRAIN_MONTHS)]
    iso = IsolationForest(n_estimators=300, contamination="auto", random_state=seed).fit(train[FEATURES])
    out["score_anomaly"] = -iso.score_samples(out[FEATURES])
    gb = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                        class_weight="balanced", random_state=seed)
    gb.fit(train[FEATURES], train.fraud)
    out["score_supervised"] = gb.predict_proba(out[FEATURES])[:, 1]
    # what a controls team actually wants to minimise: expected dollars lost, not case count.
    # exposure = what the account billed plus what it claimed this month (both known at review time)
    out["exposure"] = out.billed + out.claim_amount
    out["score_expected_loss"] = out.score_supervised * out.exposure
    # hybrid: high-severity theft controls (volume spike, shared device, mule address) jump the
    # queue, because the model has seen too few takeovers to rank them reliably on its own
    escalate = (out.R1_volume_spike | out.R4_shared_device | out.R6_mule_address).astype(bool)
    out["score_hybrid"] = out.score_expected_loss + 1e7 * escalate
    return out


METHODS = {"rules": "score_rules", "anomaly": "score_anomaly", "supervised": "score_supervised",
           "expected_loss": "score_expected_loss", "hybrid": "score_hybrid"}


def queue_at(test: pd.DataFrame, score: str, k: int) -> pd.DataFrame:
    """Top-k account-months per month by score: the cases analysts would open."""
    return test.sort_values(score, ascending=False).groupby("month").head(k)


def evaluate(scored: pd.DataFrame, capacities=(25, 50, 100, 150)) -> dict:
    test = scored[scored.month.isin(TEST_MONTHS)]
    total_fraud = int(test.fraud.sum())
    total_dollars = float(test.dollars_at_risk.sum())
    res = {"test_account_months": len(test), "test_fraud_cases": total_fraud,
           "test_dollars_at_risk": round(total_dollars, 2), "methods": {}}
    for name, col in METHODS.items():
        m = {"pr_auc": round(float(average_precision_score(test.fraud, test[col])), 3), "at_capacity": {}}
        for k in capacities:
            q = queue_at(test, col, k)
            caught = q[q.fraud == 1]
            m["at_capacity"][k] = {
                "precision": round(float(q.fraud.mean()), 3),
                "recall": round(float(len(caught) / total_fraud), 3),
                "dollars_caught": round(float(caught.dollars_at_risk.sum()), 2),
                "dollar_share": round(float(caught.dollars_at_risk.sum() / total_dollars), 3),
                "by_scheme": {s: round(float((q.schemes.str.contains(s) & (q.fraud == 1)).sum()
                                             / max(1, test.schemes.str.contains(s).sum())), 3)
                              for s in ("ATO", "UNDER", "RING")},
            }
        res["methods"][name] = m
    return res


def bootstrap_gap(scored: pd.DataFrame, k: int = 50, n_boot: int = 1000, seed: int = 7) -> dict:
    """95% interval for (supervised recall@k minus rules recall@k), resampling accounts."""
    test = scored[scored.month.isin(TEST_MONTHS)].reset_index(drop=True)
    rs = Resampler(test, seed)
    y = test.fraud.to_numpy().astype(float)
    sup, rul = test[METHODS["supervised"]].to_numpy(), test[METHODS["rules"]].to_numpy()
    gaps = []
    for _ in range(n_boot):
        idx = rs.draw()
        tf = max(1.0, y[idx].sum())
        gaps.append((top_k_sum(idx, rs.month, sup, y, k) - top_k_sum(idx, rs.month, rul, y, k)) / tf)
    lo, hi = np.percentile(gaps, [2.5, 97.5])
    return {"k": k, "mean_gap": round(float(np.mean(gaps)), 3), "ci95": [round(float(lo), 3), round(float(hi), 3)]}


def rule_report(scored: pd.DataFrame) -> pd.DataFrame:
    """Per rule on the test months: how often it fires and how often it is right."""
    test = scored[scored.month.isin(TEST_MONTHS)]
    rows = []
    for name in RULES:
        fired = test[test[name] == 1]
        rows.append({"rule": name, "fired": len(fired),
                     "precision": round(float(fired.fraud.mean()) if len(fired) else 0.0, 3),
                     "recall": round(float(fired.fraud.sum() / max(1, test.fraud.sum())), 3)})
    return pd.DataFrame(rows)
