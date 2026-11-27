"""Train, evaluate and save the models. Every run is logged to MLflow.

    python -m lade_eta train            # reads PostgreSQL
    python -m lade_eta train --source csv

Outputs in LADE_ARTIFACT_DIR: bundle.joblib (API models), metrics.json, test_scored.parquet (dashboard).
"""
from __future__ import annotations

import json
import logging
import time

import numpy as np
import pandas as pd

from . import evaluate as E
from . import features as F
from . import ingest
from .logs import log
from .models import LightGbmEta, LightGbmLateRisk, ModelBundle, RegionMedianEta, WindowAwareEta
from .settings import Settings

logger = logging.getLogger(__name__)


def load_tasks(settings: Settings, source: str) -> pd.DataFrame:
    if source == "postgres":
        return ingest.read_postgres(settings.database_url)
    ingest.download(settings)
    df, report = ingest.clean(ingest.load_csv(settings))
    log(logger, "cleaned", rows_out=report.rows_out, **report.dropped)
    return df


def evaluate_all(train, valid, test, eta, risk, baseline, window_rule, budget) -> dict:
    y_min, y_late = test[F.TARGET_MINUTES], test[F.TARGET_LATE]
    eta_pred = eta.predict(test)
    risk_score = risk.predict(test)

    # Fixed-threshold alerting: threshold chosen on the validation month, applied unchanged to test.
    flags = risk_score >= risk.threshold
    tp_lead = test.loc[flags & (y_late == 1).to_numpy(), "minutes_to_window_end"]

    eta_says_late = eta_pred > test["minutes_to_window_end"].to_numpy()
    return {
        "rows": {"train": len(train), "valid": len(valid), "test": len(test)},
        "eta": {
            "lightgbm": E.eta_metrics(y_min, eta_pred),
            "baseline_region_median": E.eta_metrics(y_min, baseline.predict(test)),
            "baseline_window_midpoint": E.eta_metrics(y_min, window_rule.predict(test)),
        },
        "late_risk": {
            "lightgbm": E.risk_metrics(y_late, risk_score, budget),
            # Rankings a team could use without a model, compared at the same alert budget.
            "rule_courier_late_rate": E.risk_metrics(y_late, test["courier_hist_late_rate"], budget),
            "rule_least_time_left": E.risk_metrics(y_late, -test["minutes_to_window_end"], budget),
            "rule_eta_model_past_window": E.alert_metrics(y_late, eta_says_late),
            "fixed_threshold_from_valid": {
                "threshold": risk.threshold,
                **E.alert_metrics(y_late, flags),
                "median_warning_minutes_before_window_end": float(tp_lead.median()) if len(tp_lead) else None,
            },
            "calibration_deciles": E.calibration_table(y_late, risk_score),
        },
        "late_rate_by_split": {
            "train": float(train[F.TARGET_LATE].mean()),
            "valid": float(valid[F.TARGET_LATE].mean()),
            "test": float(y_late.mean()),
        },
    }


def feature_importance(booster) -> dict:
    gain = booster.feature_importance(importance_type="gain")
    names = booster.feature_name()
    total = gain.sum() or 1.0
    return dict(sorted(((n, round(float(g / total), 4)) for n, g in zip(names, gain)), key=lambda kv: -kv[1]))


def run(settings: Settings, source: str = "postgres", track: bool = True) -> dict:
    t0 = time.time()
    tasks = load_tasks(settings, source)
    frame = F.build(tasks)
    train, valid, test = F.split_by_date(frame, settings.valid_start, settings.test_start, settings.reference_year)
    log(logger, "split", train=len(train), valid=len(valid), test=len(test))

    baseline = RegionMedianEta().fit(train)
    window_rule = WindowAwareEta().fit(train)
    eta = LightGbmEta().fit(train, valid, seed=settings.random_seed)
    risk = LightGbmLateRisk().fit(train, valid, seed=settings.random_seed)
    risk.set_threshold_for_budget(risk.predict(valid), settings.alert_budget)

    metrics = evaluate_all(train, valid, test, eta, risk, baseline, window_rule, settings.alert_budget)
    metrics["feature_importance"] = {"eta": feature_importance(eta.booster), "late_risk": feature_importance(risk.booster)}
    metrics["best_iterations"] = {"eta": eta.booster.best_iteration, "late_risk": risk.booster.best_iteration}
    metrics["seconds"] = round(time.time() - t0, 1)

    from .store import HistorySnapshot

    snapshot = HistorySnapshot.as_of(frame, frame["pickup_time"].max() + pd.Timedelta(days=1))
    bundle = ModelBundle(
        eta=eta, risk=risk, baseline=baseline, snapshot=snapshot,
        metadata={"city": settings.city, "alert_budget": settings.alert_budget, "features": F.FEATURES},
    )
    out = settings.artifact_dir
    bundle.save(out / "bundle.joblib")
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))

    scored = test[["order_id", "courier_id", "region_id", "aoi_id", "accept_time", "time_window_end",
                   "pickup_time", F.TARGET_MINUTES, F.TARGET_LATE, "minutes_to_window_end",
                   "courier_open_tasks"]].copy()
    scored["region_id"] = scored["region_id"].astype("int64")
    scored["eta_minutes"] = eta.predict(test)
    scored["risk"] = risk.predict(test)
    scored["flagged"] = scored["risk"] >= risk.threshold
    scored.to_parquet(out / "test_scored.parquet", index=False)

    if track:
        _log_mlflow(settings, metrics, eta, risk, out)
    log(logger, "trained", seconds=metrics["seconds"],
        eta_mae=round(metrics["eta"]["lightgbm"]["mae_min"], 1),
        pr_auc=round(metrics["late_risk"]["lightgbm"]["pr_auc"], 3))
    return metrics


def _log_mlflow(settings: Settings, metrics: dict, eta, risk, out) -> None:
    import mlflow

    mlflow.set_tracking_uri(f"sqlite:///{(out / 'mlflow.db').resolve()}")
    mlflow.set_experiment(f"lade-pickup-{settings.city}")
    with mlflow.start_run():
        mlflow.log_params({"city": settings.city, "alert_budget": settings.alert_budget,
                           "valid_start": settings.valid_start, "test_start": settings.test_start})
        mlflow.log_params({f"eta_{k}": v for k, v in eta.params.items()})
        mlflow.log_params({f"risk_{k}": v for k, v in risk.params.items() if k not in eta.params or eta.params[k] != v})
        flat = {
            "eta_mae": metrics["eta"]["lightgbm"]["mae_min"],
            "eta_mae_baseline_region": metrics["eta"]["baseline_region_median"]["mae_min"],
            "eta_mae_baseline_window": metrics["eta"]["baseline_window_midpoint"]["mae_min"],
            "risk_roc_auc": metrics["late_risk"]["lightgbm"]["roc_auc"],
            "risk_pr_auc": metrics["late_risk"]["lightgbm"]["pr_auc"],
            "risk_recall_at_budget": metrics["late_risk"]["lightgbm"]["at_budget_recall"],
            "risk_precision_at_budget": metrics["late_risk"]["lightgbm"]["at_budget_precision"],
        }
        mlflow.log_metrics({k: float(v) for k, v in flat.items() if v is not None and np.isfinite(v)})
        mlflow.log_artifact(str(out / "metrics.json"))
        mlflow.log_artifact(str(out / "bundle.joblib"))
