"""Step 1 and 2: check the randomization, then measure each email's lift."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .data import CONTROL, OUTCOMES, TREATMENTS
from .stats import compare_means, compare_proportions, holm

NUMERIC_COVARIATES = ["recency", "history"]
CATEGORICAL_COVARIATES = ["history_segment", "zip_code", "channel", "newbie", "mens", "womens"]
ARM_ORDER = ["mens", "womens", "control"]


def sample_ratio_check(df: pd.DataFrame, expected_share: dict | None = None) -> dict:
    """Sample-ratio-mismatch test: were customers split in the intended proportions?

    A broken split (e.g. a bug that drops some emailed customers) shows up here first.
    """
    counts = df["arm"].value_counts().reindex(ARM_ORDER).fillna(0).astype(int)
    shares = expected_share or {a: 1 / len(ARM_ORDER) for a in ARM_ORDER}
    expected = np.array([shares[a] for a in ARM_ORDER]) * counts.sum()
    chi2, p = stats.chisquare(counts.to_numpy(), expected)
    return {"counts": counts.to_dict(), "chi2": float(chi2), "p_value": float(p)}


def standardized_difference(x_t: np.ndarray, x_c: np.ndarray) -> float:
    """Difference in means divided by the pooled SD. |SMD| < 0.1 is the usual 'balanced' bar."""
    sd = np.sqrt((np.var(x_t, ddof=1) + np.var(x_c, ddof=1)) / 2)
    return float((np.mean(x_t) - np.mean(x_c)) / sd) if sd > 0 else 0.0


def balance_table(df: pd.DataFrame) -> pd.DataFrame:
    """Compare pre-campaign characteristics across the three groups.

    One row per covariate level: the mean (or share) in each group, the largest absolute
    standardized difference of either email group against control, and an omnibus test
    across the three groups (ANOVA for numeric, chi-square for categorical).
    """
    rows = []
    for col in NUMERIC_COVARIATES:
        groups = [df.loc[df["arm"] == a, col].to_numpy() for a in ARM_ORDER]
        _, p = stats.f_oneway(*groups)
        rows.append(_balance_row(df, col, "mean", df[col].to_numpy(float), p))
    for col in CATEGORICAL_COVARIATES:
        table = pd.crosstab(df[col], df["arm"])
        _, p, _, _ = stats.chi2_contingency(table)
        for level in sorted(df[col].unique(), key=str):
            rows.append(_balance_row(df, col, str(level), (df[col] == level).to_numpy(float), p))
    return pd.DataFrame(rows)


def _balance_row(df, col, level, values, p_value):
    by_arm = {a: values[(df["arm"] == a).to_numpy()] for a in ARM_ORDER}
    smd = max(abs(standardized_difference(by_arm[t], by_arm[CONTROL])) for t in TREATMENTS)
    return {
        "covariate": col, "level": level,
        **{a: float(by_arm[a].mean()) for a in ARM_ORDER},
        "max_abs_smd": smd, "p_value": float(p_value),
    }


def lift_table(df: pd.DataFrame, alpha: float = 0.05) -> pd.DataFrame:
    """Every email vs no email, and men's vs women's head-to-head, for all three outcomes.

    The nine tests form one family; `p_holm` adjusts for running all of them.
    """
    comparisons = [("mens", "control"), ("womens", "control"), ("mens", "womens")]
    rows = []
    for t, c in comparisons:
        dt, dc = df[df["arm"] == t], df[df["arm"] == c]
        for metric in OUTCOMES:
            if metric == "spend":
                res = compare_means(dt[metric], dc[metric], alpha)
            else:
                res = compare_proportions(
                    int(dt[metric].sum()), len(dt), int(dc[metric].sum()), len(dc), alpha
                )
            rows.append({"treatment": t, "baseline": c, "metric": metric, **res})
    out = pd.DataFrame(rows)
    out["p_holm"] = holm(out["p_value"])
    return out
