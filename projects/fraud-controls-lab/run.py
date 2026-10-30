"""Run the whole lab: generate data, check its quality, build features, score four review
queues on later months, simulate analyst capacity, and write results to outputs/.

    .venv/bin/python run.py            # full run (about 2 minutes)
    .venv/bin/python run.py --quick    # fewer simulation runs, for a fast check
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402

from fraudlab import detect, simulate  # noqa: E402
from fraudlab.features import FEATURES, build  # noqa: E402
from fraudlab.generate import generate  # noqa: E402

OUT = Path(__file__).parent / "outputs"


def data_quality(d) -> dict:
    s = d.shipments
    return {
        "accounts": len(d.accounts), "shipments": len(s), "claims": len(d.claims),
        "null_cells": int(s.isna().sum().sum() + d.claims.isna().sum().sum()),
        "non_positive_weights": int((s.measured_lb <= 0).sum()),
        "duplicate_shipment_ids": int(s.shipment_id.duplicated().sum()),
        "claims_without_shipment": int((~d.claims.shipment_id.isin(s.shipment_id)).sum()),
    }


def main(quick: bool) -> None:
    OUT.mkdir(exist_ok=True)
    d = generate()
    dq = data_quality(d)
    f, claims_scored = build(d.shipments, d.claims, d.truth)
    scored = detect.fit_models(detect.apply_rules(f))
    results = detect.evaluate(scored)
    results["data_quality"] = dq
    results["planted"] = d.truth.scheme.value_counts().to_dict()
    results["bootstrap_supervised_minus_rules_recall_at_50"] = detect.bootstrap_gap(scored, k=50,
                                                                                    n_boot=200 if quick else 1000)
    rules = detect.rule_report(scored)
    rules.to_csv(OUT / "rule_report.csv", index=False)
    results["rules"] = rules.to_dict(orient="records")

    cap = simulate.capacity_curve(scored, "score_hybrid", n_runs=200 if quick else 2000)
    cap.to_csv(OUT / "capacity.csv", index=False)
    results["capacity"] = cap.to_dict(orient="records")

    # what the supervised model leans on (permutation importance on the test months)
    test = scored[scored.month.isin(detect.TEST_MONTHS)]
    gb_train = scored[scored.month.isin(detect.TRAIN_MONTHS)]
    from sklearn.ensemble import HistGradientBoostingClassifier
    gb = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                        class_weight="balanced", random_state=7).fit(gb_train[FEATURES], gb_train.fraud)
    imp = permutation_importance(gb, test[FEATURES], test.fraud, scoring="average_precision",
                                 n_repeats=5, random_state=7)
    importance = (pd.Series(imp.importances_mean, index=FEATURES).sort_values(ascending=False).round(3))
    results["feature_importance"] = importance.head(8).to_dict()

    # text mining: the largest group of near-identical claim stories across accounts
    dup = claims_scored[claims_scored.near_dup_claims >= 5]
    results["text_mining"] = {
        "claims_with_5plus_near_duplicates_elsewhere": len(dup),
        "share_of_those_confirmed_fraud": round(float(dup.is_fraud.mean()), 3) if len(dup) else 0.0,
        "fraud_claims_flagged": round(float(dup.is_fraud.sum() / max(1, claims_scored.is_fraud.sum())), 3),
        "example_scripted": claims_scored[claims_scored.is_fraud].narrative.head(2).tolist(),
        "example_genuine": claims_scored[~claims_scored.is_fraud].narrative.head(2).tolist(),
    }
    # network: clusters of 3+ linked accounts in the final month
    last = scored[scored.month == scored.month.max()]
    big = last[last.cluster_size >= 3]
    results["network"] = {"accounts_in_clusters_of_3plus": len(big),
                          "share_confirmed_fraud": round(float(big.fraud.mean()), 3) if len(big) else 0.0}

    (OUT / "metrics.json").write_text(json.dumps(results, indent=2, default=float))
    charts(results, cap, importance)
    print(json.dumps({k: results[k] for k in ("test_fraud_cases", "test_dollars_at_risk")}, indent=2))
    for name, m in results["methods"].items():
        a = m["at_capacity"][50]
        print(f"{name:14s} PR-AUC {m['pr_auc']:.3f} | @50/month precision {a['precision']:.2f} "
              f"recall {a['recall']:.2f} dollars {a['dollar_share']:.1%}")


def charts(results: dict, cap: pd.DataFrame, importance: pd.Series) -> None:
    colors = {"rules": "#8a8f98", "anomaly": "#c7a35a", "supervised": "#5b7fbf", "expected_loss": "#7fb8a0",
              "hybrid": "#1f6f50"}
    fig, ax = plt.subplots(figsize=(7, 4))
    for name, m in results["methods"].items():
        ks = sorted(m["at_capacity"], key=int)
        ax.plot([int(k) for k in ks], [m["at_capacity"][k]["dollar_share"] * 100 for k in ks],
                marker="o", label=name.replace("_", " "), color=colors[name])
    ax.set(xlabel="cases reviewed per month", ylabel="% of fraud dollars caught",
           title="Dollars caught by review queue (test months 8-11)")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "dollars_by_capacity.png", dpi=150)

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.fill_between(cap.capacity, cap.net_p05, cap.net_p95, alpha=0.2, color="#2f8f6b", label="90% range")
    ax.plot(cap.capacity, cap.net_mean, marker="o", color="#2f8f6b", label="mean net benefit")
    ax.set(xlabel="cases reviewed per month", ylabel="net dollars per month",
           title="Monte Carlo: net benefit of review capacity")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "capacity_simulation.png", dpi=150)

    fig, ax = plt.subplots(figsize=(7, 4))
    top = importance.head(8)[::-1]
    ax.barh(top.index, top.values, color="#5b7fbf")
    ax.set(xlabel="drop in PR-AUC when shuffled", title="What the model relies on")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "feature_importance.png", dpi=150)
    plt.close("all")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--quick", action="store_true")
    main(p.parse_args().quick)
