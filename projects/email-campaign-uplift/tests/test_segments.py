import numpy as np

from email_uplift.segments import heterogeneity_tests, segment_aggregates, segment_lifts


def test_sql_aggregates_match_pandas(df):
    agg = segment_aggregates(df)
    sql = agg[agg["dimension"] == "Channel"].set_index(["level", "arm"]).sort_index()
    pd_ = df.groupby(["channel", "arm"]).agg(
        customers=("spend", "size"), conversions=("conversion", "sum"), spend_sum=("spend", "sum"))
    np.testing.assert_array_equal(sql["customers"].to_numpy(), pd_["customers"].to_numpy())
    np.testing.assert_array_equal(sql["conversions"].to_numpy(), pd_["conversions"].to_numpy())
    np.testing.assert_allclose(sql["spend_sum"].to_numpy(), pd_["spend_sum"].to_numpy())
    # every dimension partitions the full customer base
    assert (agg.groupby("dimension")["customers"].sum() == len(df)).all()


def test_segment_lifts_find_womens_only_effect():
    from conftest import make_raw
    from email_uplift.data import prepare
    df = prepare(make_raw(n=60000, seed=4, mens_effect=0.0, womens_effect_by_womens=0.04))
    seg = segment_lifts(df)
    conv = seg[(seg.metric == "conversion") & (seg.treatment == "womens") &
               (seg.dimension == "Past purchase")].set_index("level")
    assert conv.loc["Men's only", "abs_ci_low"] < 0 < conv.loc["Men's only", "abs_ci_high"]
    assert conv.loc["Women's only", "p_holm"] < 0.05
    het = heterogeneity_tests(df)
    hit = het[(het.treatment == "womens") & (het.dimension == "Past purchase") & (het.metric == "conversion")]
    miss = het[(het.treatment == "womens") & (het.dimension == "Location") & (het.metric == "conversion")]
    assert hit["p_value"].iloc[0] < 0.001
    assert miss["p_value"].iloc[0] > 0.01
