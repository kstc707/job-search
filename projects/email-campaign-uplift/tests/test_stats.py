import numpy as np
import pytest
from statsmodels.stats.proportion import proportions_ztest

from email_uplift.stats import compare_means, compare_proportions, holm


def test_proportions_match_statsmodels_z_test():
    res = compare_proportions(120, 1000, 90, 1000)
    z, p = proportions_ztest([120, 90], [1000, 1000])
    assert res["abs_lift"] == pytest.approx(0.03)
    assert res["z"] == pytest.approx(z)
    assert res["p_value"] == pytest.approx(p)
    assert res["abs_ci_low"] < 0.03 < res["abs_ci_high"]
    assert res["rel_lift"] == pytest.approx(120 / 90 - 1)


def test_welch_matches_scipy():
    from scipy import stats
    rng = np.random.default_rng(1)
    a, b = rng.exponential(2.0, 500), rng.exponential(1.5, 700)
    res = compare_means(a, b)
    t, p = stats.ttest_ind(a, b, equal_var=False)
    assert res["z"] == pytest.approx(t)
    assert res["p_value"] == pytest.approx(p)


def test_ci_coverage_on_zero_inflated_spend():
    """95% CIs for spend should cover the true difference about 95% of the time,
    even though spend is mostly zeros with a long tail (like the real data)."""
    rng = np.random.default_rng(2)

    def draw(n, p_buy):
        return np.where(rng.random(n) < p_buy, rng.lognormal(4.5, 0.8, n), 0.0)

    true_diff = (0.012 - 0.006) * np.exp(4.5 + 0.8**2 / 2)
    covered = 0
    for _ in range(300):
        res = compare_means(draw(20000, 0.012), draw(20000, 0.006))
        covered += res["abs_ci_low"] <= true_diff <= res["abs_ci_high"]
    assert 0.91 <= covered / 300 <= 0.99


def test_holm_adjustment():
    adj = holm([0.01, 0.04, 0.03, 0.5])
    np.testing.assert_allclose(adj, [0.04, 0.09, 0.09, 0.5])
