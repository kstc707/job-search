"""Two-group comparison methods: proportions (visit, conversion) and means (spend).

Each function returns a plain dict so results can go straight into a DataFrame or JSON.
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def compare_proportions(x_t: int, n_t: int, x_c: int, n_c: int, alpha: float = 0.05) -> dict:
    """Treatment-minus-control difference in a rate.

    - p-value: two-sided two-proportion z-test with the pooled rate (the usual A/B test).
    - CI for the absolute difference: Wald interval with unpooled standard errors.
    - Relative lift (p_t / p_c - 1) with a CI from the delta method on log(p_t / p_c).
    """
    p_t, p_c = x_t / n_t, x_c / n_c
    diff = p_t - p_c
    pooled = (x_t + x_c) / (n_t + n_c)
    se_pooled = np.sqrt(pooled * (1 - pooled) * (1 / n_t + 1 / n_c))
    z = diff / se_pooled if se_pooled > 0 else 0.0
    p_value = 2 * stats.norm.sf(abs(z))
    zcrit = stats.norm.ppf(1 - alpha / 2)
    se = np.sqrt(p_t * (1 - p_t) / n_t + p_c * (1 - p_c) / n_c)
    out = {
        "treatment_rate": p_t, "control_rate": p_c, "abs_lift": diff,
        "abs_ci_low": diff - zcrit * se, "abs_ci_high": diff + zcrit * se,
        "rel_lift": np.nan, "rel_ci_low": np.nan, "rel_ci_high": np.nan,
        "z": z, "p_value": p_value, "n_treatment": n_t, "n_control": n_c,
    }
    if x_t > 0 and x_c > 0:
        log_rr = np.log(p_t / p_c)
        se_log = np.sqrt(1 / x_t - 1 / n_t + 1 / x_c - 1 / n_c)
        out.update(
            rel_lift=np.exp(log_rr) - 1,
            rel_ci_low=np.exp(log_rr - zcrit * se_log) - 1,
            rel_ci_high=np.exp(log_rr + zcrit * se_log) - 1,
        )
    return out


def compare_means_from_moments(
    sum_t: float, sumsq_t: float, n_t: int,
    sum_c: float, sumsq_c: float, n_c: int,
    alpha: float = 0.05,
) -> dict:
    """Welch's t-test and CI for a difference in means, from sums and sums of squares.

    Working from sufficient statistics lets the SQL segment query do the aggregation.
    Spend is mostly zeros with a long right tail, but with thousands of customers per group
    the sampling distribution of the mean is close to normal (checked against a bootstrap
    in the tests).
    """
    m_t, m_c = sum_t / n_t, sum_c / n_c
    var_t = max((sumsq_t - n_t * m_t**2) / (n_t - 1), 0.0)
    var_c = max((sumsq_c - n_c * m_c**2) / (n_c - 1), 0.0)
    a, b = var_t / n_t, var_c / n_c
    se = np.sqrt(a + b)
    diff = m_t - m_c
    if se == 0:
        t, dof, p_value, half = 0.0, np.nan, 1.0, 0.0
    else:
        dof = (a + b) ** 2 / (a**2 / (n_t - 1) + b**2 / (n_c - 1))
        t = diff / se
        p_value = 2 * stats.t.sf(abs(t), dof)
        half = stats.t.ppf(1 - alpha / 2, dof) * se
    return {
        "treatment_rate": m_t, "control_rate": m_c, "abs_lift": diff,
        "abs_ci_low": diff - half, "abs_ci_high": diff + half,
        "rel_lift": diff / m_c if m_c else np.nan,
        "rel_ci_low": (diff - half) / m_c if m_c else np.nan,
        "rel_ci_high": (diff + half) / m_c if m_c else np.nan,
        "z": t, "p_value": p_value, "n_treatment": n_t, "n_control": n_c,
    }


def compare_means(y_t: np.ndarray, y_c: np.ndarray, alpha: float = 0.05) -> dict:
    y_t, y_c = np.asarray(y_t, float), np.asarray(y_c, float)
    return compare_means_from_moments(
        y_t.sum(), (y_t**2).sum(), len(y_t), y_c.sum(), (y_c**2).sum(), len(y_c), alpha
    )


def holm(p_values) -> np.ndarray:
    """Holm-Bonferroni adjusted p-values (controls the family-wise error rate)."""
    p = np.asarray(p_values, float)
    order = np.argsort(p)
    m = len(p)
    adjusted = np.empty(m)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p[idx]))
        adjusted[idx] = running
    return adjusted


def mde_proportion(p_c: float, n_t: int, n_c: int, alpha: float = 0.05, power: float = 0.8) -> float:
    """Smallest absolute lift detectable with the given power (normal approximation)."""
    z = stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)
    return z * np.sqrt(p_c * (1 - p_c) * (1 / n_t + 1 / n_c))
