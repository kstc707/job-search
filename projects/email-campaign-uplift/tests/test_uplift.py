import numpy as np
import pandas as pd
import pytest

from conftest import make_raw
from email_uplift.data import prepare
from email_uplift.uplift import (
    MODEL_SPECS, cross_fit_uplift, evaluate_policies, feature_matrix, targeted_assignment,
    targeting_summary, uplift_curve,
)


@pytest.fixture(scope="module")
def hetero():
    # Women's email only works for women's buyers -> a good model must find them.
    return prepare(make_raw(n=30000, seed=5, mens_effect=0.0, womens_effect_by_womens=0.06))


def test_features_exclude_outcomes_and_group(df):
    cols = set(feature_matrix(df).columns)
    assert not cols & {"visit", "conversion", "spend", "segment", "arm"}


def test_true_uplift_ranking_beats_random(hetero):
    oracle = hetero["womens"].astype(float)  # the true driver of the effect
    curve = uplift_curve(hetero, oracle, "womens", "conversion")
    at_half = curve[np.isclose(curve["fraction"], 0.5)].iloc[0]
    assert at_half["incremental"] > at_half["incremental_random"]
    # The last point of the curve is the full campaign, equal for any ranking.
    assert curve["incremental"].iloc[-1] == pytest.approx(curve["incremental_random"].iloc[-1])


def test_cross_fitted_model_learns_the_effect(hetero):
    scores = cross_fit_uplift(MODEL_SPECS[0], hetero)
    assert scores.notna().all().all()
    by_group = scores.groupby(hetero["womens"])["womens"].mean()
    assert by_group[1] > by_group[0] + 0.02
    ts = targeting_summary(hetero, scores["womens"], "womens", 0.5, "conversion", n_boot=100)
    assert ts["extra_vs_random"] > 0
    assert ts["extra_vs_random_ci_low"] > 0


def test_random_scores_do_not_beat_random(hetero):
    noise = pd.Series(np.random.default_rng(0).random(len(hetero)), index=hetero.index)
    ts = targeting_summary(hetero, noise, "womens", 0.5, "conversion", n_boot=200)
    assert ts["extra_vs_random_ci_low"] < 0 < ts["extra_vs_random_ci_high"]


def test_targeted_assignment_shapes():
    scores = pd.DataFrame({"mens": [0.1, 0.5, 0.2, 0.0], "womens": [0.3, 0.1, 0.0, 0.05]})
    best = targeted_assignment(scores, 0.5)
    assert sorted(best) == ["control", "control", "mens", "womens"]
    assert best[1] == "mens" and best[0] == "womens"
    assert list(targeted_assignment(scores, 0.25, "mens")) == ["control", "mens", "control", "control"]


def test_policy_value_ipw_matches_known_truth(hetero):
    # Sending everyone the men's email: IPW estimate equals the men's group mean exactly.
    everyone = np.full(len(hetero), "mens", dtype=object)
    res = evaluate_policies(hetero, {"ipw": everyone, "mix": {"mens": 1.0}}, "conversion", n_boot=50)
    vals = res.set_index("policy")["per_customer"]
    assert vals["ipw"] == pytest.approx(vals["mix"])
    # Targeting women's buyers with the women's email beats sending nobody anything.
    target = np.where(hetero["womens"] == 1, "womens", "control").astype(object)
    res = evaluate_policies(hetero, {"target": target, "none": {"control": 1.0}}, "conversion",
                            reference="none", n_boot=200)
    row = res.set_index("policy").loc["target"]
    assert row["vs_reference_ci_low"] > 0
