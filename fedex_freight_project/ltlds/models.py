"""Forecasting models (fixed list in ds/PREREGISTRATION.md). Each has fit(train) and predict(test)."""
import itertools

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from . import config as C

NUMERIC = [c for g, cols in C.FEATURE_GROUPS.items() if g != "carrier" for c in cols]


class Naive:
    name = "naive"

    def fit(self, train):
        self.fallback = train["y"].mean()
        return self

    def predict(self, X):
        return X["y_l1"].fillna(self.fallback).to_numpy()


class Fallback(Naive):
    """Use a same-quarter monthly signal when one was published by tau, else last quarter's YoY."""

    def __init__(self, col, name):
        self.col, self.name = col, name

    def predict(self, X):
        return X[self.col].fillna(X["y_l1"]).fillna(self.fallback).to_numpy()


def design(X: pd.DataFrame, cols, carriers=True) -> pd.DataFrame:
    """Numeric features with missing-indicator flags, plus one-hot carrier columns."""
    D = pd.DataFrame(index=X.index)
    for c in cols:
        if c == "carrier_code":
            continue
        D[c] = X[c]
        if X[c].isna().any() or c in ("own_m", "mkt_m", "mkt_l1", "cwt_yoy_l1", "y_l4"):
            D[c + "_na"] = X[c].isna().astype(float)
    if carriers and "carrier_code" in cols:
        for i, t in enumerate(C.CARRIERS):
            D["is_" + t] = (X["carrier_code"] == i).astype(float)
    return D


class RidgeModel:
    name = "ridge"
    grid = [0.3, 1, 3, 10, 30, 100]

    def __init__(self, cols=None, alpha=None):
        self.cols = cols or (NUMERIC + ["carrier_code"])
        self.alpha = alpha

    def _fit(self, train, alpha):
        D = design(train, self.cols)
        self.columns_ = D.columns
        self.fill_ = D.median()
        self.sc_ = StandardScaler().fit(D.fillna(self.fill_))
        self.m_ = Ridge(alpha=alpha).fit(self.sc_.transform(D.fillna(self.fill_)), train["y"])
        return self

    def fit(self, train):
        self.alpha_ = self.alpha if self.alpha is not None else tune(self, train, [{"alpha": a} for a in self.grid])["alpha"]
        return self._fit(train, self.alpha_)

    def predict(self, X):
        D = design(X, self.cols).reindex(columns=self.columns_)
        return self.m_.predict(self.sc_.transform(D.fillna(self.fill_)))


class GBMModel:
    name = "gbm"
    grid = [dict(max_depth=d, learning_rate=lr, max_iter=n, min_samples_leaf=leaf)
            for d, lr, n, leaf in itertools.product([2, 3], [0.03, 0.1], [100, 300], [8, 15])]

    def __init__(self, cols=None, params=None, loss="absolute_error", quantile=None):
        self.cols = cols or (NUMERIC + ["carrier_code"])
        self.params, self.loss, self.quantile = params, loss, quantile

    def _model(self, p):
        kw = dict(loss=self.loss, random_state=C.SEED, l2_regularization=1.0, **p)
        if self.loss == "quantile":
            kw["quantile"] = self.quantile
        cats = [self.cols.index("carrier_code")] if "carrier_code" in self.cols else None
        return HistGradientBoostingRegressor(categorical_features=cats, **kw)

    def _fit(self, train, p):
        self.m_ = self._model(p).fit(train[self.cols], train["y"])
        return self

    def fit(self, train):
        self.params_ = self.params if self.params is not None else tune(self, train, self.grid)
        return self._fit(train, self.params_)

    def predict(self, X):
        return self.m_.predict(X[self.cols])


class Ensemble:
    name = "ensemble"

    def __init__(self, members):
        self.members = members

    def fit(self, train):
        for m in self.members:
            m.fit(train)
        return self

    def predict(self, X):
        return np.mean([m.predict(X) for m in self.members], axis=0)


def tune(model, train: pd.DataFrame, grid: list):
    """Nested tuning: expanding-window CV over the training set's own last INNER_ORIGINS issue dates."""
    taus = np.sort(train["tau"].unique())[-C.INNER_ORIGINS:]
    best, best_err = grid[0], np.inf
    for g in grid:
        errs = []
        for tau in taus:
            tr = train[train["known"] < tau]
            te = train[train["tau"] == tau]
            if len(tr) < 20 or te.empty:
                continue
            model._fit(tr, *(g.values() if set(g) == {"alpha"} else [g]))
            errs.extend(np.abs(model.predict(te) - te["y"]))
        if errs and np.mean(errs) < best_err:
            best, best_err = g, np.mean(errs)
    return best


def model_zoo():
    """The pre-registered model list. Fresh instances each call."""
    return {
        "naive": lambda: Naive(),
        "market": lambda: Fallback("mkt_m", "market"),
        "own_monthly": lambda: Fallback("own_m", "own_monthly"),
        "ridge": lambda: RidgeModel(),
        "gbm": lambda: GBMModel(),
        "ensemble": lambda: Ensemble([RidgeModel(), GBMModel()]),
    }


# ---------------------------------------------------------------- post-hoc models (logged in ds/DEVIATIONS.md)
class SelectRidge(RidgeModel):
    """Ridge whose feature groups are chosen inside each training set by the same nested expanding-window CV
    used for alpha (so the test rows never influence the choice)."""
    name = "ridge_select"
    SUBSETS = [["own_history", "carrier"], ["own_history", "own_monthly", "carrier"],
               ["own_history", "own_monthly", "market", "carrier"], ["own_history", "own_monthly", "price_mix", "carrier"],
               ["own_history", "own_monthly", "macro", "carrier"], list(C.FEATURE_GROUPS)]

    def fit(self, train):
        best, best_err = None, np.inf
        for groups in self.SUBSETS:
            cols = [c for g in groups for c in C.FEATURE_GROUPS[g]]
            cand = RidgeModel(cols=cols)
            taus = np.sort(train["tau"].unique())[-C.INNER_ORIGINS:]
            errs = []
            for tau in taus:
                tr, te = train[train["known"] < tau], train[train["tau"] == tau]
                if len(tr) < 20 or te.empty:
                    continue
                cand.alpha = tune(cand, tr, [{"alpha": a} for a in cand.grid])["alpha"]
                cand._fit(tr, cand.alpha)
                errs.extend(np.abs(cand.predict(te) - te["y"]))
            if errs and np.mean(errs) < best_err:
                best, best_err = groups, np.mean(errs)
        self.groups_ = best
        self.cols = [c for g in best for c in C.FEATURE_GROUPS[g]]
        self.alpha = None
        return super().fit(train)


class Hybrid:
    """Carrier's own intra-quarter monthly updates when any were filed by tau, otherwise the ML ensemble."""
    name = "hybrid"

    def fit(self, train):
        self.ml = Ensemble([RidgeModel(), GBMModel()]).fit(train)
        return self

    def predict(self, X):
        ml = self.ml.predict(X)
        return np.where(X["own_m"].notna(), X["own_m"], ml)
