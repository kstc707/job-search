import numpy as np

from email_uplift.experiment import balance_table, lift_table, sample_ratio_check


def test_random_split_passes_checks(df):
    assert sample_ratio_check(df)["p_value"] > 0.01
    bal = balance_table(df)
    assert bal["max_abs_smd"].max() < 0.1


def test_sample_ratio_check_flags_broken_split(df):
    broken = df.drop(df.index[df["arm"] == "mens"][:600])
    assert sample_ratio_check(broken)["p_value"] < 0.001


def test_balance_flags_imbalanced_assignment(df):
    # Simulate a bug: the men's email went mostly to recent customers.
    skewed = df.copy()
    recent = skewed["recency"] <= 3
    skewed.loc[recent, "arm"] = np.where(np.random.default_rng(0).random(recent.sum()) < 0.8,
                                         "mens", skewed.loc[recent, "arm"])
    bal = balance_table(skewed)
    assert bal.loc[bal["covariate"] == "recency", "max_abs_smd"].iloc[0] > 0.1


def test_lift_table_recovers_known_effect():
    from conftest import make_raw
    from email_uplift.data import prepare
    df = prepare(make_raw(n=60000, seed=3, mens_effect=0.02))
    lift = lift_table(df)
    r = lift[(lift.treatment == "mens") & (lift.baseline == "control") & (lift.metric == "conversion")].iloc[0]
    assert r.abs_ci_low < 0.02 < r.abs_ci_high
    assert r.p_holm < 0.001
    assert len(lift) == 9
