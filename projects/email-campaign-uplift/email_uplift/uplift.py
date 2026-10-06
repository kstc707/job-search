"""Step 4 and 5: an uplift model to decide who should get an email, and how much it is worth.

Vocabulary
- Uplift (also "incremental effect", "CATE"): how much more likely a customer is to buy *because*
  they got the email, i.e. P(buy | email) - P(buy | no email). A regular response model
  predicts P(buy | email) and so ranks loyal customers who would buy anyway at the top; an
  uplift model ranks the customers the email actually changes.
- T-learner ("two-model" approach): fit one model on emailed customers and one on the
  no-email group, and score uplift as the difference of their predictions. It works here
  because the experiment was randomized, so both groups are comparable.
- Cross-fitting: every customer's score comes from a model that never saw that customer,
  so evaluating the scores on the same data is not optimistic.
- Uplift curve: sort customers by score, and for the top k% compare the average outcome of
  emailed vs. not-emailed customers in that slice. That slice-level difference times the
  number of customers targeted is the incremental revenue from emailing them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .data import CONTROL, TREATMENTS

FEATURES_NUMERIC = ["recency", "history", "mens", "womens", "newbie"]
FEATURES_CATEGORICAL = ["zip_code", "channel"]


def feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Pre-campaign customer attributes only; outcomes and the group label never enter."""
    x = df[FEATURES_NUMERIC].astype(float).copy()
    x["log_history"] = np.log1p(df["history"])
    for col in FEATURES_CATEGORICAL:
        for level in sorted(df[col].unique()):
            x[f"{col}={level}"] = (df[col] == level).astype(float)
    return x


def logistic_model():
    return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))


def boosting_model():
    # Shallow, strongly regularized trees: conversions are rare (about 1 in 100), so a
    # flexible model would mostly fit noise.
    return HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=150, min_samples_leaf=200,
        l2_regularization=1.0, random_state=0,
    )


@dataclass(frozen=True)
class UpliftSpec:
    name: str
    target: str  # outcome the per-arm models predict
    make_model: Callable


MODEL_SPECS = [
    UpliftSpec("T-learner, logistic, conversion", "conversion", logistic_model),
    UpliftSpec("T-learner, boosting, conversion", "conversion", boosting_model),
    UpliftSpec("T-learner, logistic, visit", "visit", logistic_model),
    UpliftSpec("T-learner, boosting, visit", "visit", boosting_model),
]


def fit_t_learner(spec: UpliftSpec, x: pd.DataFrame, df: pd.DataFrame) -> dict:
    """One fitted outcome model per group (mens, womens, control)."""
    models = {}
    for arm in TREATMENTS + [CONTROL]:
        mask = (df["arm"] == arm).to_numpy()
        models[arm] = spec.make_model().fit(x[mask], df.loc[mask, spec.target])
    return models


def predict_uplift(models: dict, x: pd.DataFrame) -> pd.DataFrame:
    """Predicted uplift of each email for each customer (rows align with x)."""
    base = models[CONTROL].predict_proba(x)[:, 1]
    return pd.DataFrame(
        {arm: models[arm].predict_proba(x)[:, 1] - base for arm in TREATMENTS}, index=x.index
    )


def cross_fit_uplift(spec: UpliftSpec, df: pd.DataFrame, n_splits: int = 5, seed: int = 0) -> pd.DataFrame:
    """Out-of-fold uplift scores for every customer in df."""
    x = feature_matrix(df)
    strata = df["arm"] + "_" + df["conversion"].astype(str)
    scores = pd.DataFrame(index=df.index, columns=TREATMENTS, dtype=float)
    folds = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    for train_idx, test_idx in folds.split(x, strata):
        models = fit_t_learner(spec, x.iloc[train_idx], df.iloc[train_idx])
        scores.iloc[test_idx] = predict_uplift(models, x.iloc[test_idx]).to_numpy()
    return scores


def heuristic_scores(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Rules a marketer might use without a model, as baselines the model has to beat."""
    return {
        "Rule: most recent buyers first": -df["recency"].astype(float),
        "Rule: biggest past spenders first": df["history"].astype(float),
    }


# --- Evaluation --------------------------------------------------------------------------

DEFAULT_FRACTIONS = np.round(np.arange(0.05, 1.0001, 0.05), 2)


def _ranked(df: pd.DataFrame, score: pd.Series, treatment: str, outcome: str, seed: int):
    """Customers in `treatment` or control, sorted best-score first (random tie-break)."""
    sub = df["arm"].isin([treatment, CONTROL]).to_numpy()
    s = np.asarray(score, float)[sub]
    y = df[outcome].to_numpy(float)[sub]
    t = (df["arm"].to_numpy()[sub] == treatment).astype(float)
    tiebreak = np.random.default_rng(seed).random(len(s))
    order = np.lexsort((tiebreak, -s))
    return y[order], t[order]


def _curve_from_ranked(y, t, fractions, w=None):
    """Per-customer lift in the top-k slice for each k (optionally with bootstrap weights)."""
    w = np.ones_like(y) if w is None else w
    cum_ty, cum_t = np.cumsum(w * t * y), np.cumsum(w * t)
    cum_cy, cum_c = np.cumsum(w * (1 - t) * y), np.cumsum(w * (1 - t))
    idx = np.maximum(np.ceil(np.asarray(fractions) * len(y)).astype(int) - 1, 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return cum_ty[idx] / cum_t[idx] - cum_cy[idx] / cum_c[idx]


def uplift_curve(
    df: pd.DataFrame, score: pd.Series, treatment: str, outcome: str = "spend",
    population: int | None = None, fractions=DEFAULT_FRACTIONS, seed: int = 0,
) -> pd.DataFrame:
    """Incremental outcome from emailing the top-k fraction of a customer base, by k.

    `population` is the size of the customer base the result is scaled to (default: all
    customers in df). For spend the incremental column is dollars over the two-week window.
    """
    population = population or len(df)
    y, t = _ranked(df, score, treatment, outcome, seed)
    lift = _curve_from_ranked(y, t, fractions)
    overall = _curve_from_ranked(y, t, [1.0])[0]
    frac = np.asarray(fractions, float)
    return pd.DataFrame({
        "fraction": frac,
        "customers_targeted": np.round(frac * population).astype(int),
        "lift_per_targeted": lift,
        "incremental": lift * frac * population,
        "incremental_random": overall * frac * population,
    })


def targeting_summary(
    df: pd.DataFrame, score: pd.Series, treatment: str, fraction: float = 0.5,
    outcome: str = "spend", population: int | None = None, n_boot: int = 1000, seed: int = 0,
) -> dict:
    """Headline numbers for 'email only the top `fraction`', with bootstrap 95% intervals.

    The bootstrap resamples customers (Poisson weights) with the scores held fixed, so the
    intervals cover sampling noise in the evaluation, not model-refitting noise.
    """
    population = population or len(df)
    y, t = _ranked(df, score, treatment, outcome, seed)
    fr = [fraction, 1.0]

    def stats_from(lifts):
        top, overall = lifts
        model_total = top * fraction * population
        random_total = overall * fraction * population
        everyone_total = overall * population
        return {
            "incremental_model": model_total,
            "incremental_random": random_total,
            "extra_vs_random": model_total - random_total,
            "share_of_full_campaign": model_total / everyone_total if everyone_total else np.nan,
            "lift_per_targeted_model": top,
            "lift_per_targeted_random": overall,
        }

    point = stats_from(_curve_from_ranked(y, t, fr))
    rng = np.random.default_rng(seed + 1)
    boots = [stats_from(_curve_from_ranked(y, t, fr, rng.poisson(1.0, len(y))))
             for _ in range(n_boot)]
    boot = pd.DataFrame(boots)
    out = {"treatment": treatment, "outcome": outcome, "fraction": fraction,
           "population": population, **point}
    for key in ["incremental_model", "extra_vs_random", "share_of_full_campaign"]:
        out[f"{key}_ci_low"] = float(boot[key].quantile(0.025))
        out[f"{key}_ci_high"] = float(boot[key].quantile(0.975))
    out["p_extra_le_zero"] = float((boot["extra_vs_random"] <= 0).mean())
    return out


def auuc(curve: pd.DataFrame) -> float:
    """Area between the model's uplift curve and the random line, averaged over k.

    Positive means the ranking beats random targeting on average across budgets.
    """
    return float((curve["incremental"] - curve["incremental_random"]).mean())


def targeted_assignment(scores: pd.DataFrame, fraction: float, email: str | None = None,
                        seed: int = 0) -> np.ndarray:
    """Which group each customer would be put in by 'email the top `fraction` by score'.

    With `email` set, everyone selected gets that email and the score column for it is used.
    With `email=None`, each customer is scored by their best email and gets that one.
    """
    if email is None:
        best_arm = scores[TREATMENTS].idxmax(axis=1).to_numpy()
        score = scores[TREATMENTS].max(axis=1).to_numpy()
    else:
        best_arm = np.full(len(scores), email, dtype=object)
        score = scores[email].to_numpy()
    tiebreak = np.random.default_rng(seed).random(len(scores))
    order = np.lexsort((tiebreak, -score))
    k = int(round(fraction * len(scores)))
    assignment = np.full(len(scores), CONTROL, dtype=object)
    assignment[order[:k]] = best_arm[order[:k]]
    return assignment


def evaluate_policies(
    df: pd.DataFrame, policies: dict[str, np.ndarray], outcome: str = "spend",
    reference: str | None = None, n_boot: int = 1000, seed: int = 0,
) -> pd.DataFrame:
    """Outcome per customer if the whole list were treated according to each policy.

    A policy is an array saying which group (mens, womens, control) each customer would be
    put in. Because the experiment assigned groups at random with known chances, a policy's
    result can be estimated from the customers whose actual group matches the policy
    (inverse propensity weighting, self-normalized). Random policies need no matching: their
    value is a mix of the group averages, which is exact and passed in as a fraction dict.

    `reference` names the policy every other one is compared against (difference + 95% CI
    from a Poisson bootstrap over customers).
    """
    arm = df["arm"].to_numpy()
    y = df[outcome].to_numpy(float)
    propensity = df["arm"].map(df["arm"].value_counts(normalize=True)).to_numpy()

    def values(w):
        means = {a: float(((arm == a) * w * y).sum() / ((arm == a) * w).sum())
                 for a in TREATMENTS + [CONTROL]}
        out = {}
        for name, policy in policies.items():
            if isinstance(policy, dict):  # random mix, e.g. {"mens": 0.5, "control": 0.5}
                out[name] = sum(share * means[a] for a, share in policy.items())
            else:
                m = (arm == policy) * w / propensity
                out[name] = float((m * y).sum() / m.sum())
        return out

    point = values(np.ones(len(df)))
    rng = np.random.default_rng(seed)
    boot = pd.DataFrame([values(rng.poisson(1.0, len(df))) for _ in range(n_boot)])
    rows = []
    for name in policies:
        row = {"policy": name, "per_customer": point[name],
               "ci_low": float(boot[name].quantile(0.025)),
               "ci_high": float(boot[name].quantile(0.975))}
        if reference is not None:
            diff = boot[name] - boot[reference]
            row.update(vs_reference=point[name] - point[reference],
                       vs_reference_ci_low=float(diff.quantile(0.025)),
                       vs_reference_ci_high=float(diff.quantile(0.975)))
        rows.append(row)
    return pd.DataFrame(rows)
