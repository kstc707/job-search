"""Models behind one small interface: fit(frame) / predict(frame).

- RegionMedianEta: the planned baseline, typical accept-to-pickup minutes per region.
- WindowAwareEta: a stronger naive rule, "the courier comes in the middle of the window".
- LightGbmEta: gradient-boosted regression on all features (L1 loss, because MAE is the metric).
- LightGbmLateRisk: gradient-boosted classifier for P(pickup after window end).

The API and training code only see these classes, so a model can be retrained or replaced without
touching the service or notification code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from .features import CATEGORICAL, FEATURES, TARGET_LATE, TARGET_MINUTES


def _prepare(frame: pd.DataFrame, categories: dict[str, list]) -> pd.DataFrame:
    """Same columns, same category codes as training, whatever order rows or categories arrive in."""
    x = frame[FEATURES].copy()
    for col in CATEGORICAL:
        values = x[col].astype("int64")
        values = values.where(values.isin(categories[col]))  # unseen ids become missing, not an error
        x[col] = pd.Categorical(values, categories=categories[col])
    return x


@dataclass
class RegionMedianEta:
    by_region: dict[int, float] = field(default_factory=dict)
    overall: float = 0.0

    def fit(self, frame: pd.DataFrame) -> "RegionMedianEta":
        y = frame[TARGET_MINUTES]
        self.overall = float(y.median())
        self.by_region = y.groupby(frame["region_id"].astype("int64")).median().to_dict()
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return frame["region_id"].astype("int64").map(self.by_region).fillna(self.overall).to_numpy()


@dataclass
class WindowAwareEta:
    """Minutes until the window midpoint (or a minimum lag if accepted inside the window)."""

    min_minutes: float = 0.0

    def fit(self, frame: pd.DataFrame) -> "WindowAwareEta":
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        mid = (frame["minutes_to_window_start"] + frame["minutes_to_window_end"]) / 2
        return np.maximum(mid.to_numpy(), self.min_minutes)


@dataclass
class LightGbmEta:
    params: dict = field(default_factory=dict)
    booster: lgb.Booster | None = None
    categories: dict[str, list] = field(default_factory=dict)

    def fit(self, train: pd.DataFrame, valid: pd.DataFrame, seed: int = 7) -> "LightGbmEta":
        self.categories = {c: sorted(pd.concat([train[c], valid[c]]).astype("int64").unique()) for c in CATEGORICAL}
        params = {
            "objective": "l1", "learning_rate": 0.1, "num_leaves": 127, "min_data_in_leaf": 200,
            "feature_fraction": 0.9, "bagging_fraction": 0.8, "bagging_freq": 1, "seed": seed, "deterministic": True, "force_row_wise": True, "verbose": -1,
            **self.params,
        }
        self.params = params
        dtrain = lgb.Dataset(_prepare(train, self.categories), train[TARGET_MINUTES])
        dvalid = lgb.Dataset(_prepare(valid, self.categories), valid[TARGET_MINUTES], reference=dtrain)
        self.booster = lgb.train(
            params, dtrain, num_boost_round=4000, valid_sets=[dvalid],
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )
        return self

    def predict(self, frame: pd.DataFrame, num_threads: int = 0) -> np.ndarray:
        pred = self.booster.predict(_prepare(frame, self.categories), num_iteration=self.booster.best_iteration,
                                    num_threads=num_threads)
        return np.maximum(pred, 0.0)


@dataclass
class LightGbmLateRisk:
    params: dict = field(default_factory=dict)
    booster: lgb.Booster | None = None
    categories: dict[str, list] = field(default_factory=dict)
    threshold: float = 0.5  # set on the validation month to match the alert budget

    def fit(self, train: pd.DataFrame, valid: pd.DataFrame, seed: int = 7) -> "LightGbmLateRisk":
        self.categories = {c: sorted(pd.concat([train[c], valid[c]]).astype("int64").unique()) for c in CATEGORICAL}
        params = {
            "objective": "binary", "learning_rate": 0.05, "num_leaves": 63, "min_data_in_leaf": 200,
            "feature_fraction": 0.9, "bagging_fraction": 0.8, "bagging_freq": 1, "seed": seed, "deterministic": True, "force_row_wise": True, "verbose": -1,
            "metric": "average_precision", **self.params,
        }
        self.params = params
        dtrain = lgb.Dataset(_prepare(train, self.categories), train[TARGET_LATE])
        dvalid = lgb.Dataset(_prepare(valid, self.categories), valid[TARGET_LATE], reference=dtrain)
        self.booster = lgb.train(
            params, dtrain, num_boost_round=4000, valid_sets=[dvalid],
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )
        return self

    def predict(self, frame: pd.DataFrame, num_threads: int = 0) -> np.ndarray:
        return self.booster.predict(_prepare(frame, self.categories), num_iteration=self.booster.best_iteration,
                                    num_threads=num_threads)

    def set_threshold_for_budget(self, scores: np.ndarray, budget: float) -> float:
        """Threshold that flags `budget` share of tasks (e.g. 5%) on the validation month."""
        self.threshold = float(np.quantile(scores, 1 - budget))
        return self.threshold


@dataclass
class ModelBundle:
    """Everything the API needs, saved as one file."""

    eta: LightGbmEta
    risk: LightGbmLateRisk
    baseline: RegionMedianEta
    snapshot: "object"  # features.HistorySnapshot-like dict tables, see store.py
    metadata: dict = field(default_factory=dict)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @staticmethod
    def load(path: Path) -> "ModelBundle":
        return joblib.load(path)
